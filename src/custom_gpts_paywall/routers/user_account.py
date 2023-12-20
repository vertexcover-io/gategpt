from datetime import timedelta
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.exc import IntegrityError
from custom_gpts_paywall.config import DEFAULT_VERIFICATION_EXPIRY
from custom_gpts_paywall.dependencies import (
    ConfigDep,
    DbSession,
    system_api_key_auth,
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


class UserCreateResponse(UserCreateRequest):
    uuid: str
    api_key: str
    api_key_type: Literal["Bearer"] = Field(default="Bearer")
    action_schema_url: str
    privacy_policy_url: str
    prompt: str


@user_account_router.post(
    name="register_custom_gpt",
    path="/api/v1/user",
    tags=["admin"],
    status_code=201,
    response_model=UserCreateResponse,
)
def register_custom_gpt(
    request: Request,
    user_req: UserCreateRequest,
    config: ConfigDep,
    session: DbSession,
    __: None = Depends(system_api_key_auth),
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
    )
    try:
        session.add(user)
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409, detail=f"User with email {user_req.email} already exists"
        )
    session.refresh(user)
    tags = (
        "email_verification"
        if user.verification_medium == "email"
        else "oauth_verification"
    )

    return UserCreateResponse(
        name=user.name,
        gpt_name=user.gpt_name,
        gpt_url=user.gpt_url,
        email=user.email,
        verification_medium=user.verification_medium,
        gpt_description=user.gpt_description,
        token_expiry=user.token_expiry,
        uuid=user.uuid,
        api_key=user.api_key,
        action_schema_url=f"{config.domain_url}{url_for(request, 'openapi_schema_by_tags', query_params={'tags': tags})}",
        prompt=config.email_verification_prompt
        if user_req.verification_medium == "email"
        else config.oauth_verification_prompt,
        privacy_policy_url=f"{config.domain_url}{url_for('privacy_policy')}",
    )
