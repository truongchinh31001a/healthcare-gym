from datetime import datetime, timezone
from uuid import uuid4
from threading import Lock
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Boolean, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


def uid():
    return str(uuid4())


_clock_lock = Lock()
_last_timestamp = datetime.min.replace(tzinfo=timezone.utc)


def utcnow():
    # Windows clocks may return equal timestamps for successive transactions.
    # Use a process-local logical tie breaker for ingestion/audit ordering.
    from datetime import timedelta
    global _last_timestamp
    with _clock_lock:
        _last_timestamp = max(datetime.now(timezone.utc), _last_timestamp + timedelta(microseconds=1))
        return _last_timestamp


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(10), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class CredentialSession(Base):
    __tablename__ = "credential_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Consent(Base):
    __tablename__ = "consents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(40))
    granted: Mapped[bool] = mapped_column(Boolean)
    policy_version: Mapped[str] = mapped_column(String(20), default="module01-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Record(Base):
    """Sensitive JSON is encrypted; ownership and routing metadata remain queryable."""
    __tablename__ = "records"
    __table_args__ = (UniqueConstraint("user_id", "kind", "slot", name="uq_record_slot"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    slot: Mapped[str] = mapped_column(String(36), default=uid)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), nullable=True, index=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), nullable=True, index=True)
    payload: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Audit(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    subject_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(36))
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


Index("ix_consent_latest", Consent.user_id, Consent.purpose, Consent.created_at)
