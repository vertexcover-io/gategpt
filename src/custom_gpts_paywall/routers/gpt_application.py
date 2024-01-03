from datetime import timedelta
from datetime import datetime
from logging import Logger
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    validator,
    EmailStr,
)
from sqlalchemy.sql import and_
import shortuuid
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from custom_gpts_paywall.config import DEFAULT_VERIFICATION_EXPIRY, EnvConfig
from custom_gpts_paywall.dependencies import (
    ConfigDep,
    DbSession,
    LoggerDep,
    login_required,
)
from uuid import UUID, uuid4
from custom_gpts_paywall.models import (
    CustomGPTApplication,
    User,
    VerificationMedium,
    GPTAppSession,
)
from custom_gpts_paywall.utils import url_for
from custom_gpts_paywall.dependencies import get_current_user
from fastapi.responses import HTMLResponse, RedirectResponse
from custom_gpts_paywall.config import templates


gpt_application_router = APIRouter()


class RegisterGPTApplicationRequest(BaseModel):
    gpt_name: str
    gpt_url: str
    verification_medium: VerificationMedium
    gpt_description: Optional[str] = Field(default=None)
    token_expiry: timedelta = Field(default=DEFAULT_VERIFICATION_EXPIRY)


class CustomGPTApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: str = Field(default_factory=shortuuid.uuid)
    gpt_name: str
    gpt_description: Optional[str]
    gpt_url: str
    verification_medium: VerificationMedium
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


class GPTAPPSessionsResponseModel(BaseModel):
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

    limit: int | None = None
    offset: int | None = None

    @validator("limit")
    def set_max_limit(cls, v):
        if v is not None and v > 50:
            return 50
        if not v:
            return 20
        return v


def register_custom_gpt_controller(
    request: Request,
    req: RegisterGPTApplicationRequest,
    config: EnvConfig,
    session: Session,
    logger: Logger,
    current_user: User,
):
    gpt_application = CustomGPTApplication(
        gpt_name=req.gpt_name,
        gpt_description=req.gpt_description,
        gpt_url=req.gpt_url,
        verification_medium=req.verification_medium,
        token_expiry=DEFAULT_VERIFICATION_EXPIRY,
        user=current_user,
    )
    try:
        logger.info("Hello from try")
        session.add(gpt_application)
        session.flush()
        auth_details = AuthenticationDetails(
            client_id=str(gpt_application.client_id),
            client_secret=str(gpt_application.client_secret),
            authorization_url=url_for(request, "oauth2_authorize"),
            token_url=url_for(request, "oauth2_token"),
        )

        resp = RegisterGPTApplicationResponse(
            gpt_name=gpt_application.gpt_name,
            gpt_url=gpt_application.gpt_url,
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
        print("error")
        raise HTTPException(
            status_code=409,
            detail=f"An account for gpt_url {req.gpt_url} already exists",
        )


@gpt_application_router.get(
    "/api/v1/custom-gpt-application/{gpt_application_id}/gpt-app-sessions/",
    response_model=list[GPTAPPSessionsResponseModel],
)
def gpt_app_users_sesssion(
    gpt_application_id: str,
    session: DbSession,
    logger: LoggerDep,
    query_params: UserSessionQueryModel = Depends(),
):
    user_sessions_query = (
        session.query(
            GPTAppSession.email,
            GPTAppSession.name,
            GPTAppSession.created_at,
            CustomGPTApplication.uuid,
        )
        .join(CustomGPTApplication)
        .filter(CustomGPTApplication.uuid == gpt_application_id)
    )

    if query_params.name:
        user_sessions_query = user_sessions_query.filter(
            GPTAppSession.name == query_params.name
        )
    if query_params.email:
        user_sessions_query = user_sessions_query.filter(
            GPTAppSession.email == query_params.email
        )
    if query_params.start_datetime and query_params.end_datetime:
        user_sessions_query = user_sessions_query.filter(
            and_(
                GPTAppSession.created_at >= query_params.start_datetime,
                GPTAppSession.created_at <= query_params.end_datetime,
            )
        )
    elif query_params.start_datetime:
        user_sessions_query = user_sessions_query.filter(
            GPTAppSession.created_at >= query_params.start_datetime,
        )
    elif query_params.end_datetime:
        user_sessions_query = user_sessions_query.filter(
            GPTAppSession.created_at <= query_params.end_datetime,
        )

    user_sessions = user_sessions_query.limit(query_params.limit)

    if query_params.offset:
        user_sessions = user_sessions_query.offset(query_params.offset)
    if not user_sessions:
        logger.info(
            f"No user sessions found for GPT app with uuid {gpt_application_id}"
        )
        return []

    user_sessions_response = []
    for i in user_sessions:
        user_sessions_response.append(GPTAPPSessionsResponseModel.model_validate(i))

    return user_sessions_response


@gpt_application_router.get(
    "/api/v1/custom-gpt-application",
    response_model=list[CustomGPTApplicationResponse],
)
def gpt_applications(session: DbSession, logger: LoggerDep):
    gpt_apps = session.query(CustomGPTApplication).all()
    return [CustomGPTApplicationResponse.model_validate(i) for i in gpt_apps]


@gpt_application_router.get("/custom-gpt-application", response_class=HTMLResponse)
async def gpt_application_registration_view(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    return templates.TemplateResponse("registergpt.html", {"request": request})


@gpt_application_router.post(
    name="register_custom_gpt",
    path="/custom-gpt-application",
    response_model=RegisterGPTApplicationResponse,
)
def register_custom_gpt_view(
    request: Request,
    req: RegisterGPTApplicationRequest,
    config: ConfigDep,
    session: DbSession,
    logger: LoggerDep,
    current_user: User = Depends(get_current_user),
):
    register_custom_gpt_controller(
        request=request,
        req=req,
        config=config,
        session=session,
        logger=logger,
        current_user=current_user,
    )
    return RedirectResponse(url="/", status_code=302)


@gpt_application_router.post(
    name="register_custom_gpt",
    path="/api/v1/custom-gpt-application",
    status_code=201,
    response_model=RegisterGPTApplicationResponse,
)
def register_custom_gpt_api(
    request: Request,
    req: RegisterGPTApplicationRequest,
    config: ConfigDep,
    session: DbSession,
    logger: LoggerDep,
    current_user: User = Depends(get_current_user),
):
    # Extract the request parameters
    logger.info("Hello")
    logger.info(current_user.email)
    resp = register_custom_gpt_controller(
        request=request,
        req=req,
        config=config,
        session=session,
        logger=logger,
        current_user=current_user,
    )
    return resp


@gpt_application_router.get(
    "/custom-gpt-application/{gpt_application_id}/gpt-app-sessions/",
    response_model=list[GPTAPPSessionsResponseModel],
    name="gpt-app-sessions",
    include_in_schema=False,
)
def gpt_app_users_sesssion_page(
    request: Request, gpt_application_id: str, user: User = Depends(login_required)
):
    return templates.TemplateResponse(
        "gpt_app_sessions.html", context={"request": request}
    )
