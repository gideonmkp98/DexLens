import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ProductAnalyticsEvent(Base):
    """Privacy-safe product analytics telemetry event."""

    __tablename__ = "product_analytics_events"
    __table_args__ = (
        Index("ix_pae_event_name_timestamp", "event_name", "timestamp"),
        Index("ix_pae_actor_id", "actor_id"),
        Index("ix_pae_session_id", "session_id"),
        Index("ix_pae_scan_id", "scan_id"),
        Index("ix_pae_timestamp", "timestamp"),
        Index("ix_pae_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    event_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    schema_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    actor_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    actor_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    session_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    scan_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
    capture_mode: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )
    device_category: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    browser_category: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    viewport_category: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )
    processing_duration_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    confidence_state: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )
    candidate_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    is_top_suggestion_selected: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    failure_category: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    metadata_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
