import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.scan import Scan
    from app.models.user import User


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ScanFeedback(Base):
    """User and pilot feedback on scan recognition results."""

    __tablename__ = "scan_feedback"
    __table_args__ = (
        Index("ix_scan_feedback_scan_id", "scan_id"),
        Index("ix_scan_feedback_user_id", "user_id"),
        Index("ix_scan_feedback_anonymous_session_id", "anonymous_session_id"),
        Index("ix_scan_feedback_created_at", "created_at"),
        UniqueConstraint("scan_id", "owner_key", name="uq_scan_feedback_scan_owner"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    scan_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    anonymous_session_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )
    owner_key: Mapped[str] = mapped_column(
        String(41),
        Computed(
            "CASE WHEN user_id IS NOT NULL THEN CONCAT('user:', user_id) "
            "WHEN anonymous_session_id IS NOT NULL "
            "THEN CONCAT('anon:', anonymous_session_id) ELSE 'legacy' END",
            persisted=True,
        ),
    )
    feedback_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    suggested_card_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    selected_card_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    confidence_state: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )
    selected_in_candidates: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    device_category: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )

    # Relationships
    scan: Mapped["Scan"] = relationship("Scan")
    user: Mapped["User | None"] = relationship("User")
