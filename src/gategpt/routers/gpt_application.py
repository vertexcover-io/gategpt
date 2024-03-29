from datetime import timedelta
from datetime import datetime
from logging import Logger
from typing import Annotated, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    UrlConstraints,
    validator,
)
from pydantic_core import Url
from sqlalchemy import desc, func, or_
import shortuuid
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from gategpt.config import (
    DEFAULT_VERIFICATION_EXPIRY,
    EnvConfig,
    OpenAPISchemaTags,
)
from gategpt.dependencies import (
    ConfigDep,
    DbSession,
    LoggerDep,
    login_required,
)
from uuid import UUID, uuid4
from gategpt.models import (
    CustomGPTApplication,
    User,
    VerificationMedium,
    GPTAppSession,
)
from gategpt.utils import url_for
from gategpt.dependencies import get_current_user
from fastapi.responses import HTMLResponse
from gategpt.config import templates


gpt_application_router = APIRouter()


class RegisterGPTApplicationRequest(BaseModel):
    gpt_name: Annotated[str, StringConstraints(max_length=30)]
    gpt_url: Annotated[Url, UrlConstraints(allowed_schemes=["http", "https"])]
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
    token_exchange_method: Literal["Basic Auth"] = Field(default="Basic Auth")


class RegisterGPTApplicationResponse(RegisterGPTApplicationRequest):
    uuid: str
    privacy_policy_url: str
    prompt: str
    action_schema_url: str
    created_at: datetime
    authentication_details: AuthenticationDetails


class GPTAPPSessionsResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    gpt_application_id: str = Field(default_factory=shortuuid.uuid)
    email: str
    name: str
    created_at: datetime


class GPTAPPSesssionPaginatedModel(BaseModel):
    items: list[GPTAPPSessionsResponseModel]
    total_count: int


class UserSessionQueryModel(BaseModel):
    email: str | None = None
    name: str | None = None
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None

    limit: int | None = None
    offset: int | None = 0

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
        gpt_url=str(req.gpt_url),
        verification_medium=req.verification_medium,
        token_expiry=DEFAULT_VERIFICATION_EXPIRY,
        user=current_user,
    )
    try:
        session.add(gpt_application)
        session.flush()
        auth_details = AuthenticationDetails(
            client_id=str(gpt_application.client_id),
            client_secret=str(gpt_application.client_secret),
            authorization_url=url_for(request, "oauth2_server_authorize"),
            token_url=url_for(request, "oauth2_server_token"),
        )

        resp = RegisterGPTApplicationResponse(
            created_at=gpt_application.created_at,
            gpt_name=gpt_application.gpt_name,
            gpt_url=gpt_application.gpt_url,
            verification_medium=gpt_application.verification_medium,
            gpt_description=gpt_application.gpt_description,
            token_expiry=gpt_application.token_expiry,
            uuid=gpt_application.uuid,
            prompt=config.instruction_prompt,
            action_schema_url=url_for(
                request,
                "openapi_schema_by_tags",
                query_params={"tags": OpenAPISchemaTags.GPTAppSession.value},
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
    "/api/v1/custom-gpt-application/{gpt_application_id}/gpt-app-sessions",
    response_model=GPTAPPSesssionPaginatedModel,
)
def gpt_app_users_session(
    gpt_application_id: str,
    session: DbSession,
    logger: LoggerDep,
    query_params: UserSessionQueryModel = Depends(),
    user: User = Depends(get_current_user),
):
    gpt_app = (
        session.query(CustomGPTApplication)
        .filter(
            CustomGPTApplication.uuid == gpt_application_id,
            CustomGPTApplication.user_id == user.id,
        )
        .first()
    )

    if not gpt_app:
        logger.error(
            f"Unauthorized access attempt for GPT app with uuid {gpt_application_id}"
        )
        raise HTTPException(
            status_code=404,
            detail={
                "deatil": "GPT application not found or not accessible by the user"
            },
        )

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

    if query_params.name and query_params.email:
        user_sessions_query = user_sessions_query.filter(
            or_(
                GPTAppSession.name.contains(query_params.name),
                GPTAppSession.email.contains(query_params.email),
            )
        )
    elif query_params.name:
        user_sessions_query = user_sessions_query.filter(
            GPTAppSession.name.contains(query_params.name)
        )
    elif query_params.email:
        user_sessions_query = user_sessions_query.filter(
            GPTAppSession.email.containts(query_params.email)
        )

    if query_params.start_datetime:
        user_sessions_query = user_sessions_query.filter(
            GPTAppSession.created_at >= query_params.start_datetime
        )
    if query_params.end_datetime:
        user_sessions_query = user_sessions_query.filter(
            GPTAppSession.created_at <= query_params.end_datetime
        )

    total_count = (
        session.query(func.count()).select_from(user_sessions_query.subquery()).scalar()
    )

    user_sessions_query = user_sessions_query.order_by(
        desc(GPTAppSession.created_at)
    ).limit(query_params.limit)
    if query_params.offset:
        user_sessions_query = user_sessions_query.offset(query_params.offset)

    user_sessions = user_sessions_query.all()

    if not user_sessions:
        logger.info(
            f"No user sessions found for GPT app with uuid {gpt_application_id}"
        )

    paginated_response = {
        "items": user_sessions,
        "total_count": total_count,
    }

    return paginated_response


@gpt_application_router.get(
    "/api/v1/custom-gpt-application",
    response_model=list[CustomGPTApplicationResponse],
)
def gpt_applications(
    session: DbSession, logger: LoggerDep, user: User = Depends(get_current_user)
):
    gpt_apps = (
        session.query(CustomGPTApplication)
        .filter(CustomGPTApplication.user_id == user.id)
        .all()
    )
    return [CustomGPTApplicationResponse.model_validate(i) for i in gpt_apps]


@gpt_application_router.get(
    "/custom-gpt-application",
    response_class=HTMLResponse,
    name="register_custom_gpt_app_page",
    include_in_schema=False,
)
async def gpt_application_registration_view(
    request: Request,
    current_user: User = Depends(login_required),
):
    return templates.TemplateResponse("register_gpt.html", {"request": request})


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
    name="gpt_application_detail",
    path="/api/v1/custom-gpt-application/{gpt_application_id}",
    response_model=RegisterGPTApplicationResponse,
)
def gpt_application_detail(
    request: Request,
    gpt_application_id: str,
    session: DbSession,
    logger: LoggerDep,
    config: ConfigDep,
    current_user: User = Depends(get_current_user),
):
    gpt_app = (
        session.query(CustomGPTApplication)
        .filter(
            CustomGPTApplication.uuid == gpt_application_id,
            CustomGPTApplication.user_id == current_user.id,
        )
        .first()
    )

    if not gpt_app:
        logger.error(f"Gpt application with uuid {gpt_application_id}")
        raise HTTPException(
            status_code=404,
            detail={"detail": "GPT application not found"},
        )
    auth_details = AuthenticationDetails(
        client_id=str(gpt_app.client_id),
        client_secret=str(gpt_app.client_secret),
        authorization_url=url_for(request, "oauth2_server_authorize"),
        token_url=url_for(request, "oauth2_server_token"),
    )

    resp = RegisterGPTApplicationResponse(
        **gpt_app.__dict__,
        prompt=config.instruction_prompt,
        action_schema_url=url_for(
            request,
            "openapi_schema_by_tags",
            query_params={"tags": OpenAPISchemaTags.GPTAppSession.value},
        ),
        privacy_policy_url=url_for(request, "privacy_policy"),
        authentication_details=auth_details,
    )
    return resp


@gpt_application_router.get(
    name="gpt_application_detail_page",
    path="/custom-gpt-application/{gpt_application_id}",
    response_model=CustomGPTApplicationResponse,
    include_in_schema=False,
)
def gpt_application_deail_page(
    request: Request,
    gpt_application_id: str,
    current_user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(
        "gpt_application_detail.html", {"request": request}
    )


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
