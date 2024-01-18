from datetime import datetime
from logging import Logger
import logging
from typing import Annotated
from fastapi import status
from fastapi import Cookie, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from custom_gpts_paywall.config import (
    EnvConfig,
    create_config,
    parse_jwt_token,
)
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


def get_logger() -> Logger:
    return logging.getLogger(__name__)


LoggerDep = Annotated[Logger, Depends(get_logger)]


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


GPTApplicationDep = Annotated[CustomGPTApplication, Depends(gpt_application_auth)]


class JWTTokenPayload(BaseModel):
    sub: EmailStr
    exp: datetime
    iat: datetime


def parse_user(
    jwt_token: str | None, config: EnvConfig, logger: Logger, session: DbSession
) -> User | None:
    if not jwt_token:
        return None

    try:
        jwt_payload_dict = parse_jwt_token(config, jwt_token)
        jwt_payload = JWTTokenPayload(**jwt_payload_dict)
    except Exception as exc:
        logger.warn(f"Failed to parse JWT token: {exc}", exc_info=True)
        return None

    user = session.query(User).filter_by(email=jwt_payload.email).first()
    return user


def get_current_user(
    config: ConfigDep,
    logger: LoggerDep,
    session: DbSession,
    jwt_token: str = Cookie(None),
):
    user = parse_user(jwt_token, config, logger, session)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def login_required(
    request: Request,
    config: ConfigDep,
    logger: LoggerDep,
    session: DbSession,
    jwt_token: str = Cookie(None),
):
    user = parse_user(jwt_token, config, logger, session)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            detail="Failed parsing token.Redirecting to login page",
            headers={"Location": url_for(request=request, name="login_page")},
        )
    return user
