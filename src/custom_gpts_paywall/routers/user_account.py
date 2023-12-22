from datetime import timedelta
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field, HttpUrl
from sqlalchemy.exc import IntegrityError
from custom_gpts_paywall.config import DEFAULT_VERIFICATION_EXPIRY
from custom_gpts_paywall.dependencies import (
    ConfigDep,
    DbSession,
    LoggerDep,
    user_account_auth,
)
from custom_gpts_paywall.models import UserAccount, VerificationMedium
from custom_gpts_paywall.utils import url_for


user_account_router = APIRouter()


class UserCreateRequest(BaseModel):
    name: str
    gpt_name: str
    gpt_url: str
    email: EmailStr
    verification_medium: VerificationMedium
    gpt_description: Optional[str] = Field(default=None)
    token_expiry: timedelta = Field(default=DEFAULT_VERIFICATION_EXPIRY)
    store_tokens: bool = Field(default=False, exclude=True)


class AuthenticationDetails(BaseModel):
    client_id: str
    client_secret: str
    authorization_url: HttpUrl
    token_url: HttpUrl
    scope: Literal["email"] = Field(default="email")
    authentication_type: Literal["OAuth"] = Field(default="OAuth")
    token_exchange_message: Literal["Basic Auth"] = Field(default="Basic Auth")


class UserCreateResponse(UserCreateRequest):
    uuid: str
    privacy_policy_url: str
    prompt: str
    authentication_details: AuthenticationDetails


@user_account_router.post(
    name="register_custom_gpt",
    path="/api/v1/user",
    status_code=201,
    response_model=UserCreateResponse,
)
def register_custom_gpt(
    request: Request,
    user_req: UserCreateRequest,
    config: ConfigDep,
    session: DbSession,
    logger: LoggerDep,
    __: None = Depends(user_account_auth),
):
    # Extract the request parameters
    user = UserAccount(
        name=user_req.name,
        email=user_req.email,
        gpt_name=user_req.gpt_name,
        gpt_description=user_req.gpt_description,
        gpt_url=user_req.gpt_url,
        verification_medium=user_req.verification_medium,
        token_expiry=user_req.token_expiry,
        store_tokens=user_req.store_tokens,
    )
    try:
        session.add(user)
        session.flush()
        auth_details = AuthenticationDetails(
            client_id=str(user.client_id),
            client_secret=str(user.client_secret),
            authorization_url=url_for(request, "oauth2_authorize"),
            token_url=url_for(request, "oauth2_token"),
        )

        user_resp = UserCreateResponse(
            name=user.name,
            gpt_name=user.gpt_name,
            gpt_url=user.gpt_url,
            email=user.email,
            verification_medium=user.verification_medium,
            gpt_description=user.gpt_description,
            token_expiry=user.token_expiry,
            uuid=user.uuid,
            prompt=config.instruction_prompt,
            privacy_policy_url=url_for(request, "privacy_policy"),
            authentication_details=auth_details,
        )
        session.commit()
        return user_resp
    except IntegrityError as ex:
        logger.error(f"Failed to create user: {ex}", exc_info=True)
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"An account for gpt_url {user_req.gpt_url} already exists",
        )
