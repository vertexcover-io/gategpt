from datetime import datetime
from logging import Logger
import logging
from typing import Annotated
from fastapi import status
from fastapi import Cookie, Depends, HTTPException, Request
from fastapi.security import HTTPBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from gategpt.config import (
    EnvConfig,
    create_config,
    parse_jwt_token,
)
from gategpt.models import User
from gategpt.utils import url_for

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


class JWTTokenPayload(BaseModel):
    sub: EmailStr
    exp: datetime
    iat: datetime

    @property
    def email(self) -> EmailStr:
        return self.sub


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
