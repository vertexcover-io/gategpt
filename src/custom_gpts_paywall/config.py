import os
from typing import Callable, Optional
from pydantic import BaseModel, ConfigDict, Field
from dotenv import load_dotenv
from functools import cached_property
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session
from functools import lru_cache
from datetime import timedelta

DEFAULT_VERIFICATION_EXPIRY = timedelta(seconds=300)
DEFAULT_MIN_DELAY_BETWEEN_VERIFICATION = timedelta(seconds=20)
SENDPOST_API_URL = "https://api.sendpost.io/api/v1/subaccount/email/"
DEFAULT_EMAIL_FROM = "ritesh@vertexcover.io"


class EnvConfig(BaseModel):
    db_url: str
    port: int = Field(default=8000)
    sendx_api_key: Optional[str]
    min_delay_between_verification: timedelta
    email_from: str
    aws_region: str
    aws_access_key_id: str
    aws_secret_access_key: str

    @cached_property
    def db_engine(self) -> Engine:
        return create_engine(self.db_url)

    @cached_property
    def session_local(self) -> Callable[[], Session]:
        return sessionmaker(autocommit=False, autoflush=False, bind=self.db_engine)


@lru_cache()
def create_config() -> ConfigDict:
    load_dotenv()
    return EnvConfig(
        db_url=os.getenv("DATABASE_URL"),
        port=os.getenv("PORT", 8000),
        sendx_api_key=os.getenv("SENDX_API_KEY"),
        min_delay_between_verification=os.getenv(
            "MIN_DELAY_BETWEEN_VERIFICATION", DEFAULT_MIN_DELAY_BETWEEN_VERIFICATION
        ),
        email_from=os.getenv("EMAIL_FROM", DEFAULT_EMAIL_FROM),
        aws_region=os.getenv("AWS_REGION"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )
