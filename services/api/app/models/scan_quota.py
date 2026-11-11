import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ScanQuotaSetting(Base):
    """System-wide dynamic settings for scan quotas."""

    __tablename__ = "scan_quota_settings"

    key: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )
    value: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        default=None,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
        onupdate=_utcnow,
    )


class UserScanQuota(Base):
    """Per-user scan quota override settings."""

    __tablename__ = "user_scan_quotas"

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    override_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="inherit",
        server_default="inherit",
    )  # "inherit", "custom", "unlimited", "blocked"
    custom_limit: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )
    reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
        onupdate=_utcnow,
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="scan_quota",
    )


class DailyScanUsage(Base):
    """Daily scan consumption per owner and UTC date."""

    __tablename__ = "daily_scan_usage"
    __table_args__ = (
        UniqueConstraint(
            "owner_key", "usage_date", name="uq_daily_scan_usage_owner_date"
        ),
        Index("ix_daily_scan_usage_lookup", "owner_key", "usage_date"),
        Index("ix_daily_scan_usage_user_id", "user_id"),
        Index("ix_daily_scan_usage_anon_id", "anonymous_session_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    owner_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    anonymous_session_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )
    usage_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )
    used_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
        onupdate=_utcnow,
    )


class ScanIdempotencyRecord(Base):
    """Prevent duplicate quota charges for identical requests."""

    __tablename__ = "scan_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "owner_key", "idempotency_key", name="uq_scan_idempotency_owner_key"
        ),
        Index("ix_scan_idempotency_date", "usage_date"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    owner_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    scan_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    usage_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
