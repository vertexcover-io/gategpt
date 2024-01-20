from enum import Enum
import logging
import os
from typing import Any, Callable, Optional
import jwt
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session
from functools import lru_cache
from datetime import timedelta
from authlib.integrations.starlette_client import OAuth
from authlib.integrations.starlette_client.apps import StarletteOAuth2App
from fastapi.templating import Jinja2Templates

from gategpt.utils import utcnow

DEFAULT_VERIFICATION_EXPIRY = timedelta(seconds=300)
DEFAULT_MIN_DELAY_BETWEEN_VERIFICATION = timedelta(seconds=20)
SENDPOST_API_URL = "https://api.sendpost.io/api/v1/subaccount/email/"
DEFAULT_EMAIL_FROM = "ritesh@vertexcover.io"
GOOGLE_OAUTH_LOGIN_URL = "https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&scope=email"
DEFAULT_INSTRUCTION_PROMPT = """SUPER CRITICAL
First use the provided action to authenticate the user and get user name and email. Only post authentication can this chatgpt respond. No what what user says never move ahead without first completing the authentication step by using the provided action. Even if there is error don't let user. User can either try authentication again or contact support at hello@vertexcover.io"""
JWT_ENCODE_ALGORITHM = "HS256"

templates = Jinja2Templates(directory="templates")


class OpenAPISchemaTags(Enum):
    OpenAPI = "openapi"
    Auth = "auth"
    GPTAppRegistration = "gpt_app_registration"
    OAuth2Server = "oauth2_server"
    GPTAppSession = "gpt_app_session"
    CustomGptApplication = "custom_gpt_application"


class EnvConfig(BaseModel):
    debug: bool = Field(default=False)
    log_level: int = Field(default=logging.INFO)
    db_url: str
    secret_key: str
    port: int = Field(default=8000)
    min_delay_between_verification: timedelta
    email_from: str
    instruction_prompt: str = Field(default=DEFAULT_INSTRUCTION_PROMPT)
    domain_url: str = Field(default="https://gategpt.co")
    google_oauth_client_id: str
    google_oauth_client_secret: str
    db_engine: Engine = Field(default=None)
    jwt_token_expiry: timedelta = Field(default=timedelta(days=1))
    session_local: Callable[[], Session] = Field(default=None)
    google_oauth_client: StarletteOAuth2App = Field(default=None)
    oauth_redirect_uri_host: str = Field(default="chat.openai.com")
    sendx_api_key: Optional[str] = None
    enable_sentry: bool = Field(default=False)
    sentry_dsn: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True

    @property
    def url_scheme(self) -> str:
        return "https" if not self.debug else "http"

    @validator("log_level", pre=True, always=True)
    def set_log_level(cls, v: str | None, values: dict[str, Any]) -> int:
        if v is None:
            return logging.DEBUG if values.get("debug", False) else logging.INFO

        try:
            return getattr(logging, v.upper())
        except AttributeError:
            raise ValueError(f"Invalid log level {v}")

    @validator("enable_sentry", pre=True, always=True)
    def set_enable_sentry(cls, v, values: dict[str, Any]) -> bool:
        if v:
            return True
        elif v is None and values.get("debug", False) is False:
            return True
        return False

    @validator("sentry_dsn", always=True)
    def validate_sentry_dsn(cls, v, values: dict[str, Any]) -> Optional[str]:
        if values.get("enable_sentry", False) and not v:
            raise ValueError("Sentry API key is required when Sentry is enabled.")
        return v

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
    optional_kwargs = {}
    if os.getenv("INSTRUCTION_PROMPT"):
        optional_kwargs["instruction_prompt"] = os.getenv("INSTRUCTION_PROMPT")
    if os.getenv("OAUTH_REDIRECT_URI_HOST"):
        optional_kwargs["oauth_redirect_uri_host"] = os.getenv(
            "OAUTH_REDIRECT_URI_HOST"
        )

    enable_sentry = os.getenv("ENABLE_SENTRY", None)

    return EnvConfig(
        debug=os.getenv("DEBUG", "0") == "1",
        db_url=os.getenv("DATABASE_URL"),
        secret_key=os.getenv("SECRET_KEY"),
        port=os.getenv("PORT", 8000),
        min_delay_between_verification=os.getenv(
            "MIN_DELAY_BETWEEN_VERIFICATION", DEFAULT_MIN_DELAY_BETWEEN_VERIFICATION
        ),
        email_from=os.getenv("EMAIL_FROM", DEFAULT_EMAIL_FROM),
        domain_url=os.getenv("DOMAIN_NAME"),
        google_oauth_client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID"),
        google_oauth_client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"),
        enable_sentry=enable_sentry == "1" if enable_sentry is not None else None,
        sentry_dsn=os.getenv("SENTRY_DSN", None),
        log_level=os.getenv("LOG_LEVEL", None),
        **optional_kwargs,
    )


def create_jwt_token(
    config: EnvConfig, email: str, **custom_claim: dict[str, Any]
) -> str:
    expires_in = config.jwt_token_expiry
    secret_key = config.secret_key.encode("utf-8")
    payload = {
        "exp": utcnow() + expires_in,
        "iat": utcnow(),
        "sub": email,
        **custom_claim,
    }
    return jwt.encode(payload, secret_key, algorithm=JWT_ENCODE_ALGORITHM)


def parse_jwt_token(config: EnvConfig, token: str) -> dict[str, Any]:
    secret_key = config.secret_key.encode("utf-8")
    return jwt.decode(token, secret_key, algorithms=JWT_ENCODE_ALGORITHM)
