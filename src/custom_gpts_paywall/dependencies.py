from logging import Logger
import logging
from typing import Annotated
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from custom_gpts_paywall.config import EnvConfig, create_config
from custom_gpts_paywall.models import OAuthToken, CustomGPTApplication
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


def get_logger() -> Logger:
    return logging.getLogger(__name__)


LoggerDep = Annotated[Logger, Depends(get_logger)]
