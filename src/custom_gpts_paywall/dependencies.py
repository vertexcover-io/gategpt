from logging import Logger
import logging
from typing import Annotated
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from custom_gpts_paywall.config import EnvConfig, create_config
from custom_gpts_paywall.models import OAuthToken, UserAccount
from custom_gpts_paywall.utils import utcnow

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


def user_account_auth(
    db: DbSession,
    config: ConfigDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials, Depends(bearer_token_security)
    ],
) -> UserAccount:
    access_token = credentials.credentials
    user = (
        db.query(UserAccount)
        .join(OAuthToken)
        .filter(
            OAuthToken.access_token == access_token,
            OAuthToken.expires_at > utcnow(),
        )
        .first()
    )
    if user:
        return user
    elif access_token == config.api_key:
        return None
    raise HTTPException(status_code=401, detail="Invalid or missing API key")


UserDep = Annotated[UserAccount, Depends(user_account_auth)]


def get_logger() -> Logger:
    return logging.getLogger(__name__)


LoggerDep = Annotated[Logger, Depends(get_logger)]
