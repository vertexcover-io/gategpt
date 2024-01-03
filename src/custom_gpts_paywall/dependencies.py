from logging import Logger
import logging
from typing import Annotated
from fastapi import status
import jwt
from fastapi import Cookie, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from custom_gpts_paywall.config import JWT_ENCODE_ALGORITHM, EnvConfig, create_config
from custom_gpts_paywall.models import OAuthToken, CustomGPTApplication, User
from custom_gpts_paywall.utils import url_for, utcnow

config = create_config()


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


def gpt_application_auth(
    db: DbSession,
    config: ConfigDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials, Depends(bearer_token_security)
    ],
) -> CustomGPTApplication:
    access_token = credentials.credentials
    print(f"Received access token: {access_token}")
    gpt_application_auth = (
        db.query(CustomGPTApplication)
        .join(OAuthToken)
        .filter(
            OAuthToken.access_token == access_token,
            OAuthToken.expires_at > utcnow(),
        )
        .first()
    )
    if gpt_application_auth:
        print("User authenticated via OAuth")
        return gpt_application_auth
    elif access_token == config.api_key:
        print("User authenticated via API key")
        return None
    raise HTTPException(status_code=401, detail="Invalid or missing API key")


def parse_user(secret_key_bytes, jwt_token, session) -> User | None:
    secret_key_bytes = config.secret_key.encode("utf-8")

    try:
        payload = jwt.decode(
            jwt_token, secret_key_bytes, algorithms=JWT_ENCODE_ALGORITHM
        )
        user_email = payload.get("sub")

        if user_email:
            user = session.query(User).filter_by(email=user_email).first()
        else:
            return None
        return user
    except jwt.DecodeError:
        return None


def get_current_user(
    config: ConfigDep,
    session: DbSession,
    jwt_token: str = Cookie(None),
):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Not authorized :(",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if jwt_token:
        secret_key_bytes = config.secret_key.encode("utf-8")

        try:
            payload = jwt.decode(
                jwt_token, secret_key_bytes, algorithms=JWT_ENCODE_ALGORITHM
            )
            user_email = payload.get("sub")

            if user_email:
                user = session.query(User).filter_by(email=user_email).first()
            else:
                raise HTTPException(status_code=401, detail="Invalid token")
            return user
        except jwt.DecodeError:
            raise HTTPException(status_code=401, detail="Invalid token or signature")
    else:
        raise credentials_exception


def login_required(
    request: Request,
    config: ConfigDep,
    session: DbSession,
    jwt_token: str = Cookie(None),
):
    exception = HTTPException(
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        detail="Redirecting to login page",
        headers={"Location": url_for(request=request, name="login_page")},
    )

    if not jwt_token:
        raise exception
    secret_key_bytes = config.secret_key.encode("utf-8")
    user = parse_user(secret_key_bytes, jwt_token, session)
    if not user:
        raise exception
    return user


GPTApplicationDep = Annotated[CustomGPTApplication, Depends(gpt_application_auth)]


def get_logger() -> Logger:
    return logging.getLogger(__name__)


LoggerDep = Annotated[Logger, Depends(get_logger)]
