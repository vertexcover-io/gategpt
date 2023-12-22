from datetime import datetime, timezone
from typing import Annotated
import uuid
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, HttpUrl, ValidationError, field_validator
import shortuuid
from sqlalchemy.orm import joinedload
from custom_gpts_paywall.config import EnvConfig

from custom_gpts_paywall.dependencies import ConfigDep, DbSession, LoggerDep
from custom_gpts_paywall.models import (
    OAuthToken,
    OAuthVerificationRequest,
    OAuthVerificationRequestStatus,
    CustomGPTApplication,
)
from custom_gpts_paywall.utils import url_for, utcnow


oauth2_router = APIRouter()


class AuthorizationRequestParams(BaseModel):
    client_id: uuid.UUID
    redirect_uri: HttpUrl
    state: str
    scope: list[str]
    nonce: str = None

    @field_validator("scope", mode="before")
    def validate_scope(cls, v):
        if isinstance(v, str):
            return v.split(" ")
        return v


@oauth2_router.get("/authorize")
async def oauth2_authorize(
    request: Request,
    config: ConfigDep,
    session: DbSession,
):
    try:
        params = AuthorizationRequestParams(**request.query_params._dict)
    except ValidationError as e:
        raise RequestValidationError(errors=e.errors())

    gpt_application = (
        session.query(CustomGPTApplication)
        .filter(CustomGPTApplication.client_id == params.client_id)
        .first()
    )
    if not gpt_application:
        raise HTTPException(
            status_code=401,
            detail="Invalid client_id",
        )

    if params.redirect_uri.host != config.oauth_redirect_uri_host:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid redirect_uri: {params.redirect_uri.host}",
        )

    nonce = params.nonce or shortuuid.uuid()

    oauth_verification_request = OAuthVerificationRequest(
        provider="google",
        gpt_application_id=gpt_application.id,
        state=params.state,
        redirect_uri=str(params.redirect_uri),
        status=OAuthVerificationRequestStatus.IN_PROGRESS,
        oauth_flow_started_at=utcnow(),
        nonce=nonce,
    )

    session.add(oauth_verification_request)
    session.flush()
    verification_request_id = oauth_verification_request.uuid
    session.commit()
    return await config.google_oauth_client.authorize_redirect(
        request,
        redirect_uri=url_for(
            request,
            "oauth_google_callback",
            scheme=config.url_scheme,
        ),
        state=verification_request_id,
        nonce=nonce,
        access_type="offline",
    )


security = HTTPBasic()


def verify_credentials(
    credentials: Annotated[HTTPBasicCredentials, Depends(security)], session: DbSession
):
    client_id = credentials.username
    client_secret = credentials.password
    gpt_application = (
        session.query(CustomGPTApplication)
        .filter(
            CustomGPTApplication.client_id == client_id,
            CustomGPTApplication.client_secret == client_secret,
        )
        .first()
    )
    if not gpt_application:
        raise HTTPException(
            status_code=401,
            detail="Invalid client_id or client_secret",
        )

    return gpt_application


async def _fetch_access_token(
    verification_request_uuid: str,
    authorization_code: str,
    nonce: str,
    redirect_uri: str,
    config: EnvConfig,
) -> str:
    oauth_client = config.google_oauth_client
    token = await oauth_client.fetch_access_token(
        grant_type="authorization_code",
        code=authorization_code,
        nonce=nonce,
        state=verification_request_uuid,
        redirect_uri=redirect_uri,
    )
    return token


async def _fetch_user_email(
    token: dict,
    nonce: str,
    config: EnvConfig,
):
    oauth_client = config.google_oauth_client
    if "id_token" in token:
        userinfo = await oauth_client.parse_id_token(token, nonce=nonce)
        email = userinfo["email"]
        return email
    else:
        raise Exception("Unable to get user email from google oauth. Please try again")


@oauth2_router.post("/token", response_class=JSONResponse)
async def oauth2_token(
    request: Request,
    gpt_application: Annotated[CustomGPTApplication, Depends(verify_credentials)],
    session: DbSession,
    config: ConfigDep,
    grant_type: Annotated[str, Form()],
    code: Annotated[str, Form()],
    redirect_uri: Annotated[str, Form()],
    logger: LoggerDep,
):
    if grant_type != "authorization_code":
        raise HTTPException(
            status_code=400,
            detail="Invalid grant_type",
        )

    oauth_verification_request = (
        session.query(OAuthVerificationRequest)
        .filter(
            OAuthVerificationRequest.uuid == code,
            OAuthVerificationRequest.redirect_uri == redirect_uri,
            OAuthVerificationRequest.gpt_application_id == gpt_application.id,
        )
        .options(joinedload(OAuthVerificationRequest.gpt_application))
        .first()
    )
    if not oauth_verification_request:
        raise HTTPException(
            status_code=404,
            detail="Verification Request not found",
        )

    now = utcnow()
    if (
        oauth_verification_request.created_at + gpt_application.token_expiry < now
        or oauth_verification_request.status
        != OAuthVerificationRequestStatus.CALLBACK_COMPLETED
    ):
        raise HTTPException(
            status_code=422,
            detail="Either OAuth Verification Request is expired or archived. Please start again",
        )

    token = await _fetch_access_token(
        verification_request_uuid=code,
        authorization_code=oauth_verification_request.authorization_code,
        nonce=oauth_verification_request.nonce,
        redirect_uri=url_for(
            request, "oauth_google_callback", scheme=config.url_scheme
        ),
        config=config,
    )
    email = await _fetch_user_email(
        token=token, nonce=oauth_verification_request.nonce, config=config
    )
    logger.info(
        f"Successfully fetched user email: {email} and token: {token} from google oauth"
    )
    oauth_verification_request.status = OAuthVerificationRequestStatus.VERIFIED
    oauth_verification_request.verified_at = utcnow()
    oauth_verification_request.email = email
    session.add(oauth_verification_request)
    if gpt_application.store_tokens:
        oauth_token = OAuthToken(
            gpt_application_id=gpt_application.id,
            access_token=token["access_token"],
            refresh_token=token.get("refresh_token", ""),
            expires_at=datetime.utcfromtimestamp(token["expires_at"]).replace(
                tzinfo=timezone.utc
            ),
        )
        session.add(oauth_token)
    session.commit()
    token["gpt_application_id"] = gpt_application.uuid
    return token
