from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, Field, EmailStr
from typing import Annotated, Optional, Any
from fastapi import FastAPI, Depends, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from custom_gpts_paywall.config import (
    create_config,
    EnvConfig,
    DEFAULT_VERIFICATION_EXPIRY,
)
from custom_gpts_paywall.emailer import send_verification_email
from custom_gpts_paywall.models import User, VerificationMedium, VerificationRequest
from sqlalchemy.orm import Session
from datetime import timedelta
import random
from custom_gpts_paywall.utils import utcnow


config = create_config()
app = FastAPI(
    servers=[
        {
            "url": config.domain_url,
        }
    ],
    tags=[
        {
            "name": "admin",
            "description": "Admin API",
        },
        {
            "name": "openai",
            "description": "OpenAI Actions API",
        },
    ],
)


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
    action_schema: dict[str, Any]
    privacy_policy: str
    prompt: str


class JSONMessageResponse(BaseModel):
    message: str


def env_config() -> EnvConfig:
    return config


ConfigDep = Annotated[EnvConfig, Depends(env_config)]


def db_session(env_config: ConfigDep) -> Session:
    db = env_config.session_local()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(db_session)]

bearer_token_security = HTTPBearer(scheme_name="API Key")


def system_api_key_auth(
    config: ConfigDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials, Depends(bearer_token_security)
    ],
):
    api_key = credentials.credentials
    if api_key != config.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def user_api_key_auth(
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


UserDep = Annotated[User, Depends(user_api_key_auth)]


def get_openapi_schema(tags: set[str]) -> dict[str, Any]:
    openapi_schema = dict(**app.openapi())
    filtered_paths = {}

    for path, path_item in openapi_schema["paths"].items():
        for method, operation in path_item.items():
            if "tags" in operation and set(operation["tags"]) & tags:
                if path not in filtered_paths:
                    filtered_paths[path] = {}
                filtered_paths[path][method] = operation

    openapi_schema["paths"] = filtered_paths
    return openapi_schema


@app.get("/healthcheck", tags=["private"])
def healthcheck(config: ConfigDep):
    return {"status": "ok"}


@app.post(
    "/api/v1/user",
    tags=["admin"],
    status_code=201,
    response_model=UserCreateResponse,
)
def create_user(
    user_req: UserCreateRequest,
    config: ConfigDep,
    session: DbSession,
    authenticate: None = Depends(system_api_key_auth),
):
    # Extract the request parameters
    user = User(
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
    action_schema = get_openapi_schema({"openai"})
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
        action_schema=action_schema,
        prompt=config.auth_prompt,
        privacy_policy=f"{config.domain_url}/privacy-policy",
    )


class CreateVerificationRequest(BaseModel):
    email: EmailStr


@app.post(
    "/api/v1/verification-request",
    tags=["openai"],
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
        session.query(VerificationRequest)
        .filter(
            VerificationRequest.user_id == user.id,
            VerificationRequest.email == create_verification_request.email,
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
        user_id=user.id,
        otp=random.randint(10000000, 99999999),
        email=create_verification_request.email,
    )
    otp = verification_request.otp
    try:
        session.query(VerificationRequest).filter(
            VerificationRequest.user_id == user.id,
            VerificationRequest.email == create_verification_request.email,
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
        email=create_verification_request.email,
        otp=otp,
    )
    print(f"OTP {otp} has been sent to user's {user.verification_medium.value}")
    return {"message": f"OTP has been sent to user's {user.verification_medium.value}"}


class VerifyOTPRequest(BaseModel):
    otp: str
    email: EmailStr


@app.post(
    "/api/v1/verify",
    status_code=200,
    response_model=JSONMessageResponse,
    tags=["openai"],
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
            VerificationRequest.email == verify_request.email,
            VerificationRequest.otp == verify_request.otp,
            VerificationRequest.verified_at.is_(None),
            VerificationRequest.is_archived.is_(False),
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
            VerificationRequest.verified_at: utcnow(),
        }
    )
    session.commit()
    return {
        "message": "OTP has been verified successfully",
    }


@app.get(
    "/platform-openapi-schema", response_class=JSONResponse, include_in_schema=False
)
def platform_openapi_scehema():
    return get_openapi_schema({"admin"})


@app.get("/openai-openapi-schema", response_class=JSONResponse, include_in_schema=False)
def openai_openapi_scehema():
    return get_openapi_schema({"openai"})


@app.get("/privacy-policy", response_class=HTMLResponse)
async def privacy_policy():
    return """
    <html>
        <body>
            <h1>Privacy Policy for GPT Verifier</h1>
            <p><strong>Effective Date: 19th Nov, 2023</strong></p>
            <h2>Overview</h2>
            <p>GPT Verifier, powered by custom GPT technology, offers an email verification service. This privacy policy describes how we collect, use, and safeguard your personal information in relation to this service.</p>
            <h2>Data Collection</h2>
            <ol>
                <li><strong>Email Addresses:</strong> We collect email addresses submitted by users for the purpose of verification.</li>
                <li><strong>Verification Data:</strong> Information generated or related to the email verification process is also collected.</li>
            </ol>
            <h2>Use of Data</h2>
            <p>Your data is used exclusively for:</p>
            <ol>
                <li>Conducting email verification processes.</li>
                <li>Enhancing the accuracy and efficiency of our verification service.</li>
            </ol>
            <h2>Data Sharing and Disclosure</h2>
            <ol>
                <li><strong>Service Providers:</strong> We may share data with trusted third parties who assist us in operating our service, conducting our business, or serving our users, so long as those parties agree to keep this information confidential.</li>
                <li><strong>Legal Requirements:</strong> We may disclose your information when we believe release is appropriate to comply with the law, enforce our site policies, or protect ours or others' rights, property, or safety.</li>
            </ol>
            <h2>Data Security</h2>
            <p>We implement a variety of security measures to maintain the safety of your personal information.</p>
            <h2>Changes to This Policy</h2>
            <p>We reserve the right to modify this policy at any time. Changes will be posted on this page with an updated effective date.</p>
            <h2>Contact Us</h2>
            <p>For questions about this privacy policy, please contact us at contact@vertexcover.io.</p>
        </body>
    </html>
    """
