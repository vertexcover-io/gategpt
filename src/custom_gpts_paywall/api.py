from logging import Logger
import logging
import shortuuid
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from pydantic import BaseModel, Field, EmailStr
from typing import Annotated, Optional, Any, Literal, Tuple
from fastapi import FastAPI, Depends, BackgroundTasks, HTTPException, Request, Query
from starlette.middleware.sessions import SessionMiddleware

from fastapi.responses import HTMLResponse, JSONResponse

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from custom_gpts_paywall.config import (
    create_config,
    EnvConfig,
    DEFAULT_VERIFICATION_EXPIRY,
)
from custom_gpts_paywall.emailer import send_verification_email
from custom_gpts_paywall.models import (
    OAuthVerificationRequest,
    OAuthVerificationRequestStatus,
    User,
    VerificationMedium,
    EmailVerificationRequest,
)
from sqlalchemy.orm import Session
from datetime import timedelta
import random
from custom_gpts_paywall.utils import utcnow, url_for


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
            "name": "gpts",
            "description": "gpts Actions API",
        },
    ],
)

app.add_middleware(SessionMiddleware, secret_key=config.secret_key)


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


def get_logger() -> Logger:
    return logging.getLogger(__name__)


LoggerDep = Annotated[Logger, Depends(get_logger)]


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


@app.get(
    "/healthcheck",
    include_in_schema=False,
)
def healthcheck(config: ConfigDep):
    return {"status": "ok"}


@app.post(
    name="register_custom_gpt",
    path="/api/v1/user",
    tags=["admin"],
    status_code=201,
    response_model=UserCreateResponse,
)
def register_custom_gpt(
    user_req: UserCreateRequest,
    config: ConfigDep,
    session: DbSession,
    __: None = Depends(system_api_key_auth),
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
        action_schema_url=f"{config.domain_url}{app.url_path_for('openapi_schema_by_tags')}?tags={tags}",
        prompt=config.email_verification_prompt
        if user_req.verification_medium == "email"
        else config.oauth_verification_prompt,
        privacy_policy_url=f"{config.domain_url}{app.url_path_for('privacy_policy')}",
    )


class CreateVerificationRequest(BaseModel):
    email: EmailStr


@app.post(
    "/api/v1/verification-request",
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


@app.post(
    "/api/v1/oauth-verification-request",
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


@app.post(
    "/api/v1/verify",
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


@app.post("/api/v1/verify-oauth", tags=["oauth_verification"])
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


@app.get("/login/{verification_request_id}", include_in_schema=False)
async def google_oauth_login(
    request: Request,
    verification_request_id: str,
    config: ConfigDep,
    session: DbSession,
):
    now = utcnow()

    verification_request = (
        session.query(OAuthVerificationRequest)
        .filter(
            OAuthVerificationRequest.uuid == verification_request_id,
            OAuthVerificationRequest.status
            == OAuthVerificationRequestStatus.NOT_STARTED,
        )
        .first()
    )

    if not verification_request:
        raise HTTPException(
            status_code=400,
            detail="Either Verification Link is invalid or has expired. Please try again.",
        )

    user = session.query(User).filter(User.id == verification_request.user_id).first()
    if not user:
        raise HTTPException(
            status_code=400,
            detail="User not found",
        )

    if verification_request.created_at + user.token_expiry < now:
        session.query(OAuthVerificationRequest).filter(
            OAuthVerificationRequest.id == verification_request.id,
        ).update(
            {
                OAuthVerificationRequest.status: OAuthVerificationRequestStatus.EXPIRED,
            }
        )
        session.commit()
        raise HTTPException(
            status_code=422,
            detail="Login Link has expired. Please start again.",
        )

    nonce = shortuuid.uuid()
    session.query(OAuthVerificationRequest).filter(
        OAuthVerificationRequest.id == verification_request.id,
    ).update(
        {
            OAuthVerificationRequest.nonce: nonce,
            OAuthVerificationRequest.status: OAuthVerificationRequestStatus.IN_PROGRESS,
            OAuthVerificationRequest.oauth_flow_started_at: utcnow(),
        }
    )
    session.commit()
    return await config.google_oauth_client.authorize_redirect(
        request,
        redirect_uri=request.url_for(
            request,
            "oauth_google_callback",
            scheme=config.url_scheme,
        ),
        state=verification_request_id,
        nonce=nonce,
    )


class OAuthCallBackException(Exception):
    def __init__(self, status: OAuthVerificationRequestStatus, message: str) -> None:
        super().__init__(message)
        self.message = message
        self.status = status

    def __str__(self) -> str:
        return self.message


def _verify_oauth_callback_request(request: Request, logger: Logger) -> Tuple[str, str]:
    error = request.query_params.get("error", None)
    code = request.query_params.get("code", None)
    verification_request_uuid = request.query_params.get("state")
    error_description = None
    if error:
        logger.error(
            f"Error while login using google oauth: {error_description}, Verification Request UUId: {verification_request_uuid}"
        )
        error_description = request.query_params.get("error_description")
    elif code is None or verification_request_uuid is None:
        logger.error("Error while login using google oauth: State/Code is not passed")
        error_description = "Google Authentication Failed. Please try again"

    if error_description:
        raise OAuthCallBackException(
            OAuthVerificationRequestStatus.FAILED, error_description
        )

    return code, verification_request_uuid


def _verify_oauth_verification_request(
    verification_request_uuid: str, session: Session, logger: Logger
) -> OAuthVerificationRequest:
    now = utcnow()
    verification_request = (
        session.query(OAuthVerificationRequest)
        .options(joinedload(OAuthVerificationRequest.user_account))
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
            "Google Authentication Failed. Please try again",
        )
    user = verification_request.user_account
    if verification_request.created_at + user.token_expiry < now:
        logger.warn(
            f"Google Authentication Request Expired. Verification Request UUId: {verification_request_uuid}"
        )
        raise OAuthCallBackException(
            OAuthVerificationRequestStatus.EXPIRED,
            "Google Authentication Request Expired.",
        )
    elif verification_request.archived_at is not None:
        logger.warn(
            f"Google Authentication Request Archived. Verification Request UUId: {verification_request_uuid}"
        )
        raise OAuthCallBackException(
            OAuthVerificationRequestStatus.ARCHIVED,
            "Google Authentication Request Expired.",
        )

    return verification_request


@app.get(
    "/oauth/google/callback",
    include_in_schema=False,
)
async def oauth_google_callback(
    request: Request, config: ConfigDep, session: DbSession, logger: LoggerDep
):
    code = None
    http_status_code = None
    response = None
    status = None
    try:
        code, verification_request_uuid = _verify_oauth_callback_request(
            request, logger
        )
        verification_request = _verify_oauth_verification_request(
            verification_request_uuid, session, logger
        )
        status = OAuthVerificationRequestStatus.CALLBACK_COMPLETED
        response = {"authorization_code": code}
        http_status_code = 200
    except OAuthCallBackException as e:
        status = e.status
        code = None
        http_status_code = 422
        response = {"error": e.message}

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
    return JSONResponse(
        status_code=http_status_code,
        content=response,
    )


class OpenAPISchemaTags(BaseModel):
    tags: list[str]


@app.get(
    "/openapi-schema",
    response_class=JSONResponse,
    include_in_schema=False,
    name="openapi_schema_by_tags",
)
def openapi_schema_by_tags(tags: list[str] = Query([])):
    return get_openapi_schema(set(tags))


@app.get(
    "/platform-openapi-schema",
    response_class=JSONResponse,
    include_in_schema=False,
    name="platform_openapi_schema",
)
def platform_openapi_scehema():
    return get_openapi_schema({"admin"})


@app.get(
    "/gpts-openapi-schema",
    response_class=JSONResponse,
    include_in_schema=False,
    name="gpts_openapi_schema",
)
def gpts_openapi_scehema(tag: str = Query(None)):
    tags = {tag} if tag else {"email_verification", "oauth_verification"}
    return get_openapi_schema(tags)


@app.get("/privacy-policy", response_class=HTMLResponse, name="privacy_policy")
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
