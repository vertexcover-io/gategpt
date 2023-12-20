# Create a model to for user account in sqlalchmey
from sqlalchemy import (
    String,
    Boolean,
    Interval,
    func,
    Enum as EnumColumn,
    Text,
    ForeignKey,
)
from sqlalchemy.orm import DeclarativeBase, declared_attr, relationship
from sqlalchemy.orm import Mapped
from sqlalchemy import DateTime
from sqlalchemy.orm import mapped_column
from datetime import datetime, timedelta
from enum import Enum
import shortuuid
from custom_gpts_paywall.config import DEFAULT_VERIFICATION_EXPIRY
from custom_gpts_paywall.utils import utcnow


class Base(DeclarativeBase):
    pass


class VerificationMedium(Enum):
    Email = "email"
    Phone = "phone"
    Google = "google"

    def __str__(self):
        return self.value


class UserAccount(Base):
    __tablename__ = "user_account"

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(22), default=shortuuid.uuid)
    name: Mapped[str] = mapped_column(String(30))
    gpt_name: Mapped[str] = mapped_column(String(30))
    gpt_description: Mapped[str] = mapped_column(Text(), nullable=True)
    gpt_url: Mapped[str] = mapped_column(Text(), unique=True)
    email: Mapped[str] = mapped_column(String(255))
    verification_medium: Mapped[VerificationMedium] = mapped_column(
        EnumColumn(VerificationMedium, native_enum=False)
    )
    token_expiry: Mapped[timedelta] = mapped_column(
        Interval, default=func.interval(DEFAULT_VERIFICATION_EXPIRY.microseconds)
    )
    api_key: Mapped[str] = mapped_column(String(22), default=shortuuid.uuid)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, name={self.name!r}, email_address={self.email})"


class BaseVerificationRequest(Base):
    __abstract__ = True
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_account.id"))

    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    archived_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    @declared_attr
    def user_account(cls):
        return relationship("UserAccount")


class EmailVerificationRequest(BaseVerificationRequest):
    __tablename__ = "email_verification_request"
    email: Mapped[str] = mapped_column(String(255))
    otp: Mapped[str] = mapped_column(String(8))


class OAuthVerificationRequestStatus(Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    CALLBACK_COMPLETED = "callback_completed"
    VERIFIED = "verified"
    FAILED = "failed"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class OAuthVerificationRequest(BaseVerificationRequest):
    __tablename__ = "oauth_verification_request"
    uuid: Mapped[str] = mapped_column(String(22), default=shortuuid.uuid)
    provider: Mapped[str] = mapped_column(String(30))
    email: Mapped[str] = mapped_column(String(255), nullable=True)
    authorization_code: Mapped[str] = mapped_column(String(255), nullable=True)
    nonce: Mapped[str] = mapped_column(String(22), nullable=True)
    status: Mapped[OAuthVerificationRequestStatus] = mapped_column(
        EnumColumn(OAuthVerificationRequestStatus, native_enum=False),
        default=OAuthVerificationRequestStatus.NOT_STARTED,
    )
    oauth_flow_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    oauth_callback_completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
