# Create a model to for user account in sqlalchmey
from sqlalchemy import ForeignKey
from sqlalchemy import String, Boolean, Interval, func, Enum as EnumColumn
from sqlalchemy.orm import DeclarativeBase
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

    def __str__(self):
        return self.value


class User(Base):
    __tablename__ = "user_account"

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(22), default=shortuuid.uuid)
    name: Mapped[str] = mapped_column(String(30))
    email: Mapped[str] = mapped_column(String(255), unique=True)
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


class VerificationRequest(Base):
    __tablename__ = "verification_request"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_account.id"))
    email: Mapped[str] = mapped_column(String(255))
    otp: Mapped[str] = mapped_column(String(8))
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
