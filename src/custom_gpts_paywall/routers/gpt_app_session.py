from datetime import datetime
from logging import Logger
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from custom_gpts_paywall.config import EnvConfig, parse_jwt_token
from custom_gpts_paywall.dependencies import (
    ConfigDep,
    DbSession,
    LoggerDep,
    JWTTokenPayload,
)
from custom_gpts_paywall.models import CustomGPTApplication, GPTAppSession


gpt_app_session_router = APIRouter()


class CreateSessionJWTTokenPayload(JWTTokenPayload):
    name: str
    gpt_application_id: str


class CreateSessionResponse(BaseModel):
    gpt_application_id: str
    email: str
    name: str


bearer_token_security = HTTPBearer(scheme_name="API Key")


def parse_create_session_jwt_token(
    token: str | None,
    config: EnvConfig,
    logger: Logger,
) -> CreateSessionJWTTokenPayload:
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Missing OAuth token",
        )

    try:
        token_payload_dict = parse_jwt_token(config, token)
        return CreateSessionJWTTokenPayload(**token_payload_dict)
    except Exception as exc:
        logger.warn("Error while parsing session JWT token", exc_info=exc)
        raise HTTPException(
            status_code=401,
            detail="Invalid OAuth token",
        )


class GPTAppSessionResponse(BaseModel):
    gpt_application_id: str
    email: str
    name: str
    created_at: datetime


@gpt_app_session_router.post("/session", response_model=CreateSessionResponse)
def create_session(
    config: ConfigDep,
    session: DbSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials, Depends(bearer_token_security)
    ],
    logger: LoggerDep,
):
    create_session_request = parse_create_session_jwt_token(
        credentials.credentials, config, logger
    )

    gpt_application = (
        session.query(CustomGPTApplication)
        .filter(CustomGPTApplication.id == create_session_request.gpt_application_id)
        .first()
    )
    if not gpt_application:
        raise HTTPException(status_code=404, detail="GPT Application not found")

    logger.info(
        f"New Session Request for: {gpt_application.uuid} with user info: {create_session_request}"
    )

    gpt_session = GPTAppSession(
        gpt_application_id=gpt_application.id,
        email=create_session_request.email,
        name=create_session_request.name,
    )
    session.add(gpt_session)
    session.commit()
    logger.info(f"New Session Created: {gpt_session}")
    return gpt_session
