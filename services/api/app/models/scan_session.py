import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.scan import Scan


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ScanSession(Base):
    """Scan session entity for continuous multi-card scanning batches."""

    __tablename__ = "scan_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'completed', 'abandoned')",
            name="ck_scan_sessions_status",
        ),
        Index("ix_scan_sessions_status_created_at", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        server_default="active",
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
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        default=None,
    )

    # Relationships
    scans: Mapped[list["Scan"]] = relationship(
        "Scan",
        back_populates="session",
        order_by="Scan.created_at.asc()",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            f"<ScanSession(id='{self.id}', status='{self.status}', "
            f"created_at='{self.created_at}')>"
        )
