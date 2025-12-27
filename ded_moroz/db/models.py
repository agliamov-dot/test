from __future__ import annotations

import enum
from datetime import datetime, date
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
    BigInteger,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


_enum_values = {"values_callable": lambda enum_cls: [item.value for item in enum_cls]}


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"


class SafetyStatus(str, enum.Enum):
    SAFE = "safe"
    NEEDS_REVIEW = "needs_review"
    BLOCKED = "blocked"


class GiftType(str, enum.Enum):
    TEXT = "text"
    URL = "url"
    PAYLOAD = "payload"
    PHOTO = "photo"
    VIDEO = "video"
    AUDIO = "audio"


class NotificationType(str, enum.Enum):
    REMINDER = "reminder"
    MISSED = "missed"


class SeverityLevel(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, **_enum_values), default=UserStatus.ACTIVE, nullable=False
    )
    opted_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())

    submissions: Mapped[list[Submission]] = relationship("Submission", back_populates="user")


class Gift(Base):
    __tablename__ = "gifts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    gift_text: Mapped[str | None] = mapped_column(String)
    gift_url: Mapped[str | None] = mapped_column(String)
    gift_type: Mapped[GiftType] = mapped_column(Enum(GiftType, **_enum_values), default=GiftType.TEXT, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_submission_user_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    day: Mapped[int] = mapped_column(Integer, nullable=False)
    poem_text: Mapped[str] = mapped_column(String, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    ded_moroz_reply: Mapped[str] = mapped_column(String, nullable=False)
    scores: Mapped[dict[str, Any] | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"))
    reasons: Mapped[dict[str, Any] | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"))
    safety_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    safety_status: Mapped[SafetyStatus] = mapped_column(
        Enum(SafetyStatus, **_enum_values), default=SafetyStatus.SAFE, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship("User", back_populates="submissions")


class PoemAttempt(Base):
    __tablename__ = "poem_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    day: Mapped[int] = mapped_column(Integer, nullable=False)
    poem_text: Mapped[str] = mapped_column(String, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    ded_moroz_reply: Mapped[str] = mapped_column(String, nullable=False)
    scores: Mapped[dict[str, Any] | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"))
    reasons: Mapped[dict[str, Any] | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"))
    safety_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    safety_status: Mapped[SafetyStatus] = mapped_column(
        Enum(SafetyStatus, **_enum_values), default=SafetyStatus.SAFE, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship("User")


class NotificationLog(Base):
    __tablename__ = "notifications_log"
    __table_args__ = (UniqueConstraint("user_id", "notification_type", "day", name="uq_notification_user_day_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    day: Mapped[int] = mapped_column(Integer, nullable=False)
    notification_type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType, **_enum_values), nullable=False
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship("User")


class ErrorLog(Base):
    __tablename__ = "error_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_name: Mapped[str | None] = mapped_column(String(255))
    level: Mapped[SeverityLevel] = mapped_column(Enum(SeverityLevel, **_enum_values), nullable=False)
    message: Mapped[str] = mapped_column(String, nullable=False)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ServiceHeartbeat(Base):
    __tablename__ = "service_heartbeats"
    __table_args__ = (UniqueConstraint("service_name", name="uq_service_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_beat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    beat_interval_seconds: Mapped[int] = mapped_column(Integer, default=600, nullable=False)


class AdminErrorQueue(Base):
    __tablename__ = "admin_error_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    error_log_id: Mapped[int] = mapped_column(ForeignKey("error_logs.id", ondelete="CASCADE"), nullable=False)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    error: Mapped[ErrorLog] = relationship("ErrorLog")
