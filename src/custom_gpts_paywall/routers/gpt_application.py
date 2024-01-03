from datetime import timedelta
from datetime import datetime
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl
from sqlalchemy.sql import and_
import shortuuid
from sqlalchemy.exc import IntegrityError
from custom_gpts_paywall.config import DEFAULT_VERIFICATION_EXPIRY
from custom_gpts_paywall.dependencies import (
    ConfigDep,
    DbSession,
    LoggerDep,
    gpt_application_auth,
)
from uuid import UUID, uuid4
from custom_gpts_paywall.models import (
    CustomGPTApplication,
    UserSession,
    VerificationMedium,
)
from custom_gpts_paywall.utils import url_for


gpt_application_router = APIRouter(prefix="/custom-gpt-application")


class RegisterGPTApplicationRequest(BaseModel):
    name: str
    gpt_name: str
    gpt_url: str
    email: EmailStr
    verification_medium: VerificationMedium
    gpt_description: Optional[str] = Field(default=None)
    token_expiry: timedelta = Field(default=DEFAULT_VERIFICATION_EXPIRY)
    store_tokens: bool = Field(default=False, exclude=True)


class CustomGPTApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: str = Field(default_factory=shortuuid.uuid)
    name: str
    gpt_name: str
    gpt_description: Optional[str]
    gpt_url: str
    email: EmailStr
    verification_medium: VerificationMedium
    store_tokens: bool = False
    token_expiry: timedelta
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    client_id: UUID = Field(default_factory=uuid4)
    client_secret: UUID = Field(default_factory=uuid4)


class AuthenticationDetails(BaseModel):
    client_id: str
    client_secret: str
    authorization_url: HttpUrl
    token_url: HttpUrl
    scope: Literal["email"] = Field(default="email")
    authentication_type: Literal["OAuth"] = Field(default="OAuth")
    token_exchange_message: Literal["Basic Auth"] = Field(default="Basic Auth")


class RegisterGPTApplicationResponse(RegisterGPTApplicationRequest):
    uuid: str
    privacy_policy_url: str
    prompt: str
    action_schema_url: str
    authentication_details: AuthenticationDetails


class UserSessionResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    gpt_application_id: str = Field(default_factory=shortuuid.uuid)
    email: str
    name: str
    created_at: datetime


class UserSessionQueryModel(BaseModel):
    email: EmailStr | None = None
    name: str | None = None
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None


@gpt_application_router.post(
    name="register_custom_gpt",
    path="",
    status_code=201,
    response_model=RegisterGPTApplicationResponse,
)
def register_custom_gpt(
    request: Request,
    req: RegisterGPTApplicationRequest,
    config: ConfigDep,
    session: DbSession,
    logger: LoggerDep,
    __: None = Depends(gpt_application_auth),
):
    # Extract the request parameters
    gpt_application = CustomGPTApplication(
        name=req.name,
        email=req.email,
        gpt_name=req.gpt_name,
        gpt_description=req.gpt_description,
        gpt_url=req.gpt_url,
        verification_medium=req.verification_medium,
        token_expiry=req.token_expiry,
        store_tokens=req.store_tokens,
    )
    try:
        session.add(gpt_application)
        session.flush()
        auth_details = AuthenticationDetails(
            client_id=str(gpt_application.client_id),
            client_secret=str(gpt_application.client_secret),
            authorization_url=url_for(request, "oauth2_authorize"),
            token_url=url_for(request, "oauth2_token"),
        )

        resp = RegisterGPTApplicationResponse(
            name=gpt_application.name,
            gpt_name=gpt_application.gpt_name,
            gpt_url=gpt_application.gpt_url,
            email=gpt_application.email,
            verification_medium=gpt_application.verification_medium,
            gpt_description=gpt_application.gpt_description,
            token_expiry=gpt_application.token_expiry,
            uuid=gpt_application.uuid,
            prompt=config.instruction_prompt,
            action_schema_url=url_for(
                request, "openapi_schema_by_tags", query_params={"tags": "auth"}
            ),
            privacy_policy_url=url_for(request, "privacy_policy"),
            authentication_details=auth_details,
        )
        session.commit()
        return resp
    except IntegrityError as ex:
        logger.error(f"Failed to create user: {ex}", exc_info=True)
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"An account for gpt_url {req.gpt_url} already exists",
        )


@gpt_application_router.get(
    "/{gpt_application_id}/user-sessions/",
    response_model=list[UserSessionResponseModel],
)
def gpt_app_users_sesssion(
    gpt_application_id: str,
    session: DbSession,
    logger: LoggerDep,
    query_params: UserSessionQueryModel = Depends(),
):
    user_sessions_query = (
        session.query(
            UserSession.email,
            UserSession.name,
            UserSession.created_at,
            CustomGPTApplication.uuid,
        )
        .join(CustomGPTApplication)
        .filter(CustomGPTApplication.uuid == gpt_application_id)
    )

    if query_params.name:
        user_sessions_query = user_sessions_query.filter(
            UserSession.name == query_params.name
        )
    if query_params.email:
        user_sessions_query = user_sessions_query.filter(
            UserSession.email == query_params.email
        )
    if query_params.start_datetime and query_params.end_datetime:
        user_sessions_query = user_sessions_query.filter(
            and_(
                UserSession.created_at >= query_params.start_datetime,
                UserSession.created_at <= query_params.end_datetime,
            )
        )
    elif query_params.start_datetime:
        user_sessions_query = user_sessions_query.filter(
            UserSession.created_at >= query_params.start_datetime,
        )
    elif query_params.end_datetime:
        user_sessions_query = user_sessions_query.filter(
            UserSession.created_at <= query_params.end_datetime,
        )

    user_sessions = user_sessions_query.all()

    if not user_sessions:
        logger.info(
            f"No user sessions found for GPT app with uuid {gpt_application_id}"
        )
        return []

    user_sessions_response = []
    for i in user_sessions:
        user_sessions_response.append(UserSessionResponseModel.model_validate(i))

    return user_sessions_response


# for testing
@gpt_application_router.get(
    "",
    response_model=list[CustomGPTApplicationResponse],
)
def gpt_applications(session: DbSession, logger: LoggerDep):
    gpt_apps = session.query(CustomGPTApplication).all()
    return [CustomGPTApplicationResponse.model_validate(i) for i in gpt_apps]
