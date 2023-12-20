from logging import Logger
import random
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from custom_gpts_paywall.config import EnvConfig

from custom_gpts_paywall.dependencies import (
    ConfigDep,
    UserDep,
    DbSession,
    LoggerDep,
)
from custom_gpts_paywall.emailer import send_verification_email
from custom_gpts_paywall.models import (
    EmailVerificationRequest,
    OAuthVerificationRequest,
    OAuthVerificationRequestStatus,
    VerificationMedium,
)
from custom_gpts_paywall.utils import url_for, utcnow


verification_router = APIRouter()


class CreateVerificationRequest(BaseModel):
    email: EmailStr


class JSONMessageResponse(BaseModel):
    message: str


@verification_router.post(
    "/verification-request",
    name="start_email_verification",
    tags=["email_verification"],
    status_code=202,
    response_model=JSONMessageResponse,
)
def create_verification_request(
    config: ConfigDep,
    create_verification_request: CreateVerificationRequest,
    user: UserDep,
    session: DbSession,
    bg_tasks: BackgroundTasks,
):
    now = utcnow()
    last_verification_request = (
        session.query(EmailVerificationRequest)
        .filter(
            EmailVerificationRequest.user_id == user.id,
            EmailVerificationRequest.email == create_verification_request.email,
            (
                EmailVerificationRequest.created_at
                + config.min_delay_between_verification
            )
            > now,
        )
        .order_by(EmailVerificationRequest.created_at.desc())
        .first()
    )

    if last_verification_request:
        raise HTTPException(
            status_code=429,
            detail="Too many verification requests. Please try again after some time",
        )

    verification_request = EmailVerificationRequest(
        user_id=user.id,
        otp=random.randint(10000000, 99999999),
        email=create_verification_request.email,
    )
    otp = verification_request.otp
    try:
        session.query(EmailVerificationRequest).filter(
            EmailVerificationRequest.user_id == user.id,
            EmailVerificationRequest.email == create_verification_request.email,
        ).update({EmailVerificationRequest.archived_at: utcnow()})
        session.add(verification_request)
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    bg_tasks.add_task(
        send_verification_email,
        env_config=config,
        user=user,
        email=create_verification_request.email,
        otp=otp,
    )
    print(f"OTP {otp} has been sent to user's {user.verification_medium.value}")
    return {"message": f"OTP has been sent to user's {user.verification_medium.value}"}


class CreateOAuthVerificationRequest(BaseModel):
    provider: str = Field(default="google")


class CreateOAuthVerificationResponse(BaseModel):
    provider: str
    oauth_verification_request_id: str
    login_url: str


@verification_router.post(
    "/oauth-verification-request",
    tags=["oauth_verification"],
    status_code=202,
    response_model=CreateOAuthVerificationResponse,
)
def start_oauth_verification(
    request: Request,
    config: ConfigDep,
    create_verification_request: CreateOAuthVerificationRequest,
    user: UserDep,
    session: DbSession,
):
    if VerificationMedium.Google != user.verification_medium:
        raise HTTPException(
            status_code=400,
            detail="Custom GPT: {user.gpt_name} doesn't support oauth verification",
        )

    oauth_verification_request = OAuthVerificationRequest(
        user_id=user.id,
        provider=create_verification_request.provider,
    )
    try:
        session.add(oauth_verification_request)
        session.commit()
    except Exception as e:
        session.rollback()
        raise e

    return CreateOAuthVerificationResponse(
        provider=create_verification_request.provider,
        oauth_verification_request_id=oauth_verification_request.uuid,
        login_url=url_for(
            request,
            "google_oauth_login",
            verification_request_id=oauth_verification_request.uuid,
            scheme=config.url_scheme,
        ),
    )


class VerifyOTPRequest(BaseModel):
    otp: str
    email: EmailStr


@verification_router.post(
    "/verify",
    name="verify_email_otp",
    status_code=200,
    response_model=JSONMessageResponse,
    tags=["email_verification"],
)
def verify_otp(
    verify_request: VerifyOTPRequest,
    config: ConfigDep,
    session: DbSession,
    user: UserDep,
):
    now = utcnow()
    verification_request = (
        session.query(EmailVerificationRequest)
        .filter(
            EmailVerificationRequest.user_id == user.id,
            EmailVerificationRequest.email == verify_request.email,
            EmailVerificationRequest.otp == verify_request.otp,
            EmailVerificationRequest.verified_at.is_(None),
            EmailVerificationRequest.archived_at.is_(None),
            (EmailVerificationRequest.created_at + user.token_expiry) > now,
        )
        .first()
    )
    if not verification_request:
        raise HTTPException(
            status_code=400,
            detail="Either OTP is invalid or has expired. Please try again.",
        )

    session.query(EmailVerificationRequest).filter(
        EmailVerificationRequest.id == verification_request.id,
    ).update(
        {
            EmailVerificationRequest.verified_at: utcnow(),
        }
    )
    session.commit()
    return {
        "message": "OTP has been verified successfully",
    }


class VerifyOAuthRequest(BaseModel):
    verification_request_id: str
    code: str


class VerifyOAuthResponse(BaseModel):
    is_verified: bool
    message: str


async def _get_user_email_from_oauth(
    verification_request_uuid: str,
    authorization_code: str,
    nonce: str,
    redirect_uri: str,
    config: EnvConfig,
    logger: Logger,
) -> str:
    oauth_client = config.google_oauth_client
    token = await oauth_client.fetch_access_token(
        code=authorization_code,
        nonce=nonce,
        state=verification_request_uuid,
        redirect_uri=redirect_uri,
    )
    if "id_token" in token:
        userinfo = await oauth_client.parse_id_token(token, nonce=nonce)
        email = userinfo["email"]
        return email
    else:
        logger.error(
            f"Unable to get user email from google oauth. Verification Request uuid: {verification_request_uuid}"
        )
        raise Exception("Unable to get user email from google oauth. Please try again")


@verification_router.post("/verify-oauth", tags=["oauth_verification"])
async def verify_oauth(
    request: Request,
    verify_request: VerifyOAuthRequest,
    config: ConfigDep,
    session: DbSession,
    user: UserDep,
    logger: LoggerDep,
):
    oauth_verification_request = (
        session.query(OAuthVerificationRequest)
        .filter(
            OAuthVerificationRequest.uuid == verify_request.verification_request_id,
            OAuthVerificationRequest.user_id == user.id,
        )
        .first()
    )
    if not oauth_verification_request:
        raise HTTPException(
            status_code=404,
            detail="Verification Request not found",
        )

    now = utcnow()
    if (
        oauth_verification_request.created_at + user.token_expiry < now
        or oauth_verification_request.status
        in [
            OAuthVerificationRequestStatus.ARCHIVED,
            OAuthVerificationRequestStatus.EXPIRED,
            OAuthVerificationRequestStatus.FAILED,
            OAuthVerificationRequestStatus.VERIFIED,
        ]
    ):
        raise HTTPException(
            status_code=400,
            detail="Either OAuth Verification Request is expired or archived. Please start again",
        )

    elif (
        oauth_verification_request.status
        != OAuthVerificationRequestStatus.CALLBACK_COMPLETED
    ):
        return VerifyOAuthResponse(
            is_verified=False,
            message=f"OAuth Verification Request is in status {oauth_verification_request.status}. Please verify after some",
        )

    elif oauth_verification_request.authorization_code != verify_request.code:
        print(oauth_verification_request.authorization_code, verify_request.code)
        raise HTTPException(
            status_code=400,
            detail="Authorization code does not match",
        )

    elif oauth_verification_request.created_at + user.token_expiry < now:
        raise HTTPException(
            status_code=400,
            detail="OAuth Verification Request has expired. Please start again",
        )

    email = await _get_user_email_from_oauth(
        authorization_code=oauth_verification_request.authorization_code,
        nonce=oauth_verification_request.nonce,
        verification_request_uuid=verify_request.verification_request_id,
        redirect_uri=url_for(
            request, "oauth_google_callback", scheme=config.url_scheme
        ),
        config=config,
        logger=logger,
    )
    oauth_verification_request.status = OAuthVerificationRequestStatus.VERIFIED
    oauth_verification_request.verified_at = utcnow()
    oauth_verification_request.email = email
    session.commit()
    return {
        "is_verified": True,
        "message": "OAuth has been verified successfully",
    }
