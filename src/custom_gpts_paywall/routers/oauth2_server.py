from logging import Logger
from typing import Annotated, TypedDict
from urllib.parse import urlencode
import uuid
from authlib.integrations.httpx_client import AsyncOAuth2Client
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import httpx
from pydantic import BaseModel, HttpUrl, ValidationError, field_validator
import shortuuid
from sqlalchemy.orm import Session, joinedload
from custom_gpts_paywall.config import EnvConfig, create_jwt_token

from custom_gpts_paywall.dependencies import ConfigDep, DbSession, LoggerDep
from custom_gpts_paywall.models import (
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


class OAuth2ServerToken(TypedDict):
    access_token: str
    expires_in: int
    id_token: str


class GoogleUserInfo(TypedDict):
    email: str
    name: str


@oauth2_router.get("/authorize")
async def oauth2_server_authorize(
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
            "oauth2_server_callback_google",
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
) -> OAuth2ServerToken:
    oauth_client = config.google_oauth_client
    token = await oauth_client.fetch_access_token(
        grant_type="authorization_code",
        code=authorization_code,
        nonce=nonce,
        state=verification_request_uuid,
        redirect_uri=redirect_uri,
    )
    return token


async def _fetch_google_user_profile(access_token: str) -> GoogleUserInfo:
    client = AsyncOAuth2Client(token={"access_token": access_token})

    userinfo_endpoint = "https://www.googleapis.com/oauth2/v3/userinfo"

    response = await client.get(userinfo_endpoint)
    return await response.json()


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


class OAuth2ServerTokenResponse(BaseModel):
    email: str
    name: str
    access_token: str


@oauth2_router.post("/token", response_class=JSONResponse)
async def oauth2_server_token(
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
            request, "oauth2_server_callback_google", scheme=config.url_scheme
        ),
        config=config,
    )
    access_token = token["access_token"]
    try:
        user_info = await _fetch_google_user_profile(access_token)
    except (httpx.RequestError, httpx.httpx.NetworkError) as exc:
        logger.error(
            f"A network error occurred while fetching user_info: {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail="Network Error while fetching user_info"
        )
    except httpx.HTTPStatusError as exc:
        error_msg = "Error while validating token"
        logger.errror(
            f"Error while fetching user profile: Status Code: {exc.response.status_code}. Response: {exc.response.content}",
            exc_info=exc,
        )
        raise HTTPException(status_code=exc.response.status_code, detail=error_msg)

    email = user_info["email"]
    name = user_info["name"]
    jwt_token = create_jwt_token(
        config,
        email=email,
        name=name,
    )

    logger.info(
        f"Successfully fetched user email: {email} and name: {name} from google oauth"
    )

    oauth_verification_request.status = OAuthVerificationRequestStatus.VERIFIED
    oauth_verification_request.verified_at = utcnow()
    oauth_verification_request.email = email
    session.add(oauth_verification_request)
    session.commit()
    return {
        "name": name,
        "email": email,
        "gpt_application_id": oauth_verification_request.gpt_application_id,
        "access_token": jwt_token,
    }


class OAuthCallBackException(Exception):
    def __init__(
        self, status: OAuthVerificationRequestStatus, error_code: str, message: str
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status = status

    def __str__(self) -> str:
        return self.message


def _verify_oauth_callback_request(request: Request, logger: Logger) -> tuple[str, str]:
    error_code = request.query_params.get("error", None)
    code = request.query_params.get("code", None)
    verification_request_uuid = request.query_params.get("state")
    error_description = None
    if error_code:
        logger.error(
            f"Error while login using google oauth: {error_description}, Verification Request UUId: {verification_request_uuid}"
        )
        error_description = request.query_params.get("error_description")

    elif code is None:
        logger.error("Error while login using google oauth: Code is not passed")
        error_code = "invalid_request"
        error_description = "Missing authorization  code"
    elif verification_request_uuid is None:
        logger.error("Error while login using google oauth: State is not passed")
        error_code = "invalid_request"
        error_description = "Missing state"

    if error_description:
        raise OAuthCallBackException(
            OAuthVerificationRequestStatus.FAILED, error_code, error_description
        )

    return code, verification_request_uuid


def _verify_oauth_verification_request(
    verification_request_uuid: str, session: Session, logger: Logger
) -> OAuthVerificationRequest:
    now = utcnow()
    verification_request = (
        session.query(OAuthVerificationRequest)
        .options(joinedload(OAuthVerificationRequest.gpt_application))
        .filter(
            OAuthVerificationRequest.uuid == verification_request_uuid,
        )
        .first()
    )
    if not verification_request:
        logger.error(
            f"Error while login using google oauth: Invalid verification_request_uuid: {verification_request_uuid}"
        )
        raise OAuthCallBackException(
            OAuthVerificationRequestStatus.FAILED,
            "server_error",
            "Google Authentication Failed. Please try again",
        )
    gpt_application = verification_request.gpt_application
    if verification_request.created_at + gpt_application.token_expiry < now:
        logger.warn(
            f"Google Authentication Request Expired. Verification Request UUId: {verification_request_uuid}"
        )
        raise OAuthCallBackException(
            OAuthVerificationRequestStatus.EXPIRED,
            "access_denied",
            "Google Authentication Request Expired.",
        )
    elif verification_request.archived_at is not None:
        logger.warn(
            f"Google Authentication Request Archived. Verification Request UUId: {verification_request_uuid}"
        )
        raise OAuthCallBackException(
            OAuthVerificationRequestStatus.ARCHIVED,
            "access_denied" "Google Authentication Request Expired.",
        )

    return verification_request


@oauth2_router.get(
    "/callback/google",
)
async def oauth2_server_callback_google(
    request: Request, config: ConfigDep, session: DbSession, logger: LoggerDep
):
    code = None
    status = None
    try:
        code, verification_request_uuid = _verify_oauth_callback_request(
            request, logger
        )
        verification_request = _verify_oauth_verification_request(
            verification_request_uuid, session, logger
        )
        status = OAuthVerificationRequestStatus.CALLBACK_COMPLETED
        query_params = {
            "code": verification_request.uuid,
            "state": verification_request.state,
        }
    except OAuthCallBackException as e:
        status = e.status
        code = None
        query_params = {
            "error": e.error_code,
            "error_description": e.message,
            "state": verification_request.state,
        }

    query = urlencode(query_params)
    redirect_uri = f"{verification_request.redirect_uri}?{query}"

    session.query(OAuthVerificationRequest).filter(
        OAuthVerificationRequest.id == verification_request.id,
    ).update(
        {
            OAuthVerificationRequest.status: status,
            OAuthVerificationRequest.oauth_callback_completed_at: utcnow(),
            OAuthVerificationRequest.authorization_code: code,
        }
    )
    session.commit()
    logger.info(f"After Google OAuth Callback redirecting to: {redirect_uri}")
    return RedirectResponse(url=redirect_uri)
