from datetime import timedelta
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy.exc import IntegrityError
from custom_gpts_paywall.config import DEFAULT_VERIFICATION_EXPIRY
from custom_gpts_paywall.dependencies import (
    ConfigDep,
    DbSession,
    LoggerDep,
)
from custom_gpts_paywall.models import CustomGPTApplication, VerificationMedium, User
from custom_gpts_paywall.utils import url_for
from custom_gpts_paywall.routers.auth import get_current_user
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


templates = Jinja2Templates(directory="templates")


gpt_application_router = APIRouter()


@gpt_application_router.get("/gpt-application", response_class=HTMLResponse)
async def gpt_application_registration(request: Request):
    return templates.TemplateResponse("registergpt.html", {"request": request})


class RegisterGPTApplicationRequest(BaseModel):
    gpt_name: str
    gpt_url: str
    verification_medium: VerificationMedium
    gpt_description: Optional[str] = Field(default=None)
    token_expiry: timedelta = Field(default=DEFAULT_VERIFICATION_EXPIRY)


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


@gpt_application_router.post(
    name="register_custom_gpt",
    path="/api/v1/custom-gpt-application",
    status_code=201,
    response_model=RegisterGPTApplicationResponse,
)
def register_custom_gpt(
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
