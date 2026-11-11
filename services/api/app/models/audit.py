import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class AdminAuditLog(Base):
    """Append-only audit trail for administrative operations."""

    __tablename__ = "admin_audit_logs"
    __table_args__ = (
        Index("ix_admin_audit_logs_actor_id", "actor_id"),
        Index("ix_admin_audit_logs_action", "action"),
        Index("ix_admin_audit_logs_target", "target_type", "target_id"),
        Index("ix_admin_audit_logs_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    actor_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    target_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    metadata_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    ip_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
