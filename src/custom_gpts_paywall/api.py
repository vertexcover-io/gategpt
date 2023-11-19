from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, Field, EmailStr
from typing import Annotated
from fastapi import FastAPI, Depends, Security, Header, BackgroundTasks, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from custom_gpts_paywall.config import (
    create_config,
    EnvConfig,
    DEFAULT_VERIFICATION_EXPIRY,
)
from custom_gpts_paywall.emailer import send_verification_email
from custom_gpts_paywall.models import User, VerificationMedium, VerificationRequest
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import random
from custom_gpts_paywall.utils import utcnow

app = FastAPI()


class UserCreateRequest(BaseModel):
    name: str
    email: EmailStr
    verification_medium: VerificationMedium
    token_expiry: timedelta = Field(default=DEFAULT_VERIFICATION_EXPIRY)


class UserCreateResponse(UserCreateRequest):
    uuid: str
    api_key: str


def env_config() -> EnvConfig:
    return create_config()


ConfigDep = Annotated[EnvConfig, Depends(env_config)]


def db_session(env_config: ConfigDep) -> Session:
    db = env_config.session_local()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(db_session)]

bearer_token_security = HTTPBearer(scheme_name="API Key")


def api_key_auth(
    db: DbSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials, Depends(bearer_token_security)
    ],
) -> User:
    api_key = credentials.credentials
    user = db.query(User).filter(User.api_key == api_key).first()
    if user:
        return user
    raise HTTPException(status_code=401, detail="Invalid or missing API key")


UserDep = Annotated[User, Depends(api_key_auth)]


@app.get("/healthcheck")
def healthcheck(config: ConfigDep):
    return {"status": "ok"}


@app.post(
    "/api/v1/user",
    status_code=201,
    response_model=UserCreateResponse,
)
def create_user(user_req: UserCreateRequest, config: ConfigDep, session: DbSession):
    # Extract the request parameters
    user = User(
        name=user_req.name,
        email=user_req.email,
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
    return user


@app.post(
    "/api/v1/verification-request",
    status_code=202,
)
def create_verification_request(
    config: ConfigDep, user: UserDep, session: DbSession, bg_tasks: BackgroundTasks
):
    now = utcnow()
    last_verification_request = (
        session.query(VerificationRequest)
        .filter(
            VerificationRequest.user_id == user.id,
            (VerificationRequest.created_at + config.min_delay_between_verification)
            > now,
        )
        .order_by(VerificationRequest.created_at.desc())
        .first()
    )

    if last_verification_request:
        raise HTTPException(
            status_code=429,
            detail="Too many verification requests. Please try again after some time",
        )

    verification_request = VerificationRequest(
        user_id=user.id, otp=random.randint(10000000, 99999999), is_verified=False
    )
    otp = verification_request.otp
    try:
        session.query(VerificationRequest).filter(
            VerificationRequest.user_id == user.id,
        ).update({VerificationRequest.is_archived: True})
        session.add(verification_request)
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    bg_tasks.add_task(
        send_verification_email,
        env_config=config,
        user=user,
        otp=otp,
    )

    return {
        "message": f"OTP {otp} has been sent to user's {user.verification_medium.value}"
    }


class VerifyOTPRequest(BaseModel):
    otp: str


@app.post(
    "/api/v1/verify",
    status_code=200,
)
def verify_otp(
    verify_request: VerifyOTPRequest,
    config: ConfigDep,
    session: DbSession,
    user: UserDep,
):
    now = utcnow()
    verification_request = (
        session.query(VerificationRequest)
        .filter(
            VerificationRequest.user_id == user.id,
            VerificationRequest.otp == verify_request.otp,
            VerificationRequest.is_verified == False,
            VerificationRequest.is_archived == False,
            (VerificationRequest.created_at + user.token_expiry) > now,
        )
        .first()
    )
    if not verification_request:
        raise HTTPException(
            status_code=400,
            detail="Either OTP is invalid or has expired. Please try again.",
        )

    session.query(VerificationRequest).filter(
        VerificationRequest.id == verification_request.id,
    ).update(
        {
            VerificationRequest.is_verified: True,
            VerificationRequest.verified_at: utcnow(),
        }
    )
    return {
        "message": "OTP has been verified successfully",
    }
