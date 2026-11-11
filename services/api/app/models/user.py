import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.collection import CollectionItem
    from app.models.scan import Scan


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    """Collector user account for personal collections and authenticated scans."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="user",
        server_default="user",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        server_default="active",
        index=True,
    )

    @property
    def verification_status(self) -> str:
        """Derived verification status reconciled with account state."""
        return "verified" if self.is_active else "unverified"

    @property
    def scan_quota_override(self) -> int | None:
        """Scan quota overrides are managed externally via QuotaService."""
        return getattr(self, "_scan_quota_override", None)

    @scan_quota_override.setter
    def scan_quota_override(self, value: int | None) -> None:
        self._scan_quota_override = value

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

    # Relationships
    sessions: Mapped[list["UserSession"]] = relationship(
        "UserSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    collection_items: Mapped[list["CollectionItem"]] = relationship(
        "CollectionItem",
        back_populates="user",
    )
    scans: Mapped[list["Scan"]] = relationship(
        "Scan",
        back_populates="user",
    )


class UserSession(Base):
    """Session entity for tracking authenticated or anonymous user sessions."""

    __tablename__ = "user_sessions"
    __table_args__ = (
        Index("ix_user_sessions_user_id", "user_id"),
        Index("ix_user_sessions_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    session_token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    session_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="anonymous",
        server_default="anonymous",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
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
    ip_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Relationship
    user: Mapped["User | None"] = relationship(
        "User",
        back_populates="sessions",
    )
