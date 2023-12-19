import os
from typing import Any, Callable, Optional
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session
from functools import lru_cache
from datetime import timedelta
from authlib.integrations.starlette_client import OAuth
from authlib.integrations.starlette_client.apps import StarletteOAuth2App

DEFAULT_VERIFICATION_EXPIRY = timedelta(seconds=300)
DEFAULT_MIN_DELAY_BETWEEN_VERIFICATION = timedelta(seconds=20)
SENDPOST_API_URL = "https://api.sendpost.io/api/v1/subaccount/email/"
DEFAULT_EMAIL_FROM = "ritesh@vertexcover.io"
GOOGLE_OAUTH_LOGIN_URL = "https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&scope=email"


class EnvConfig(BaseModel):
    db_url: str
    secret_key: str
    port: int = Field(default=8000)
    api_key: str
    sendx_api_key: Optional[str]
    min_delay_between_verification: timedelta
    email_from: str
    aws_region: str
    aws_access_key_id: str
    aws_secret_access_key: str
    email_verification_prompt: str
    oauth_verification_prompt: str
    domain_url: str = Field(default="http://localhost:8000")
    google_oauth_client_id: str
    google_oauth_client_secret: str
    db_engine: Engine = Field(default=None)
    session_local: Callable[[], Session] = Field(default=None)
    google_oauth_client: StarletteOAuth2App = Field(default=None)

    class Config:
        arbitrary_types_allowed = True

    @validator("db_engine", pre=True, always=True)
    def set_db_engine(cls, v, values: dict[str, Any]) -> Engine:
        db_url = values.get("db_url", None)
        if not db_url:
            return None
        return create_engine(db_url)

    @validator("session_local", pre=True, always=True)
    def set_session_local(cls, v, values: dict[str, Any]) -> Callable[[], Session]:
        db_engine = values.get("db_engine", None)
        if not db_engine:
            return None
        return sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    @validator("google_oauth_client", pre=True, always=True)
    def set_google_oauth_client(cls, v, values: dict[str, Any]) -> StarletteOAuth2App:
        print("Inside Validator")
        google_oauth_client_id = values.get("google_oauth_client_id", None)
        google_oauth_client_secret = values.get("google_oauth_client_secret", None)
        if not google_oauth_client_id or not google_oauth_client_secret:
            return None
        oauth = OAuth()
        oauth.register(
            "google",
            client_id=google_oauth_client_id,
            client_secret=google_oauth_client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
        return oauth.google


@lru_cache()
def create_config() -> EnvConfig:
    load_dotenv()
    print("Loading envconfig")
    return EnvConfig(
        db_url=os.getenv("DATABASE_URL"),
        secret_key=os.getenv("SECRET_KEY"),
        port=os.getenv("PORT", 8000),
        api_key=os.getenv("API_KEY"),
        sendx_api_key=os.getenv("SENDX_API_KEY"),
        min_delay_between_verification=os.getenv(
            "MIN_DELAY_BETWEEN_VERIFICATION", DEFAULT_MIN_DELAY_BETWEEN_VERIFICATION
        ),
        email_from=os.getenv("EMAIL_FROM", DEFAULT_EMAIL_FROM),
        aws_region=os.getenv("AWS_REGION"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        oauth_verification_prompt=os.getenv("OAUTH_VERIFICATION_PROMPT"),
        email_verification_prompt=os.getenv("AUTH_PROMPT"),
        domain_url=os.getenv("DOMAIN_NAME"),
        google_oauth_client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID"),
        google_oauth_client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"),
    )
