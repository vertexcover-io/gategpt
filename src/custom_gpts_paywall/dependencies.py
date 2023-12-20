from logging import Logger
import logging
from typing import Annotated
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from custom_gpts_paywall.config import EnvConfig, create_config
from custom_gpts_paywall.models import UserAccount

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
) -> UserAccount:
    api_key = credentials.credentials
    user = db.query(UserAccount).filter(UserAccount.api_key == api_key).first()
    if user:
        return user
    raise HTTPException(status_code=401, detail="Invalid or missing API key")


UserDep = Annotated[UserAccount, Depends(user_api_key_auth)]


def get_logger() -> Logger:
    return logging.getLogger(__name__)


LoggerDep = Annotated[Logger, Depends(get_logger)]
