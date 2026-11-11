import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.beta_access import BetaCodeRedemption, Invitation
    from app.models.collection import CollectionItem
    from app.models.scan import Scan
    from app.models.scan_quota import UserScanQuota


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
    username: Mapped[str | None] = mapped_column(
        String(50),
        unique=True,
        nullable=True,
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
    # Phase 9: Administrative status
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        server_default="active",
        index=True,
    )

    # Phase 9: Account Security
    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )
    policies_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    username_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    # Phase 9: Beta Access & Entitlements
    has_beta_access: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )
    beta_entitlement: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    registration_mode_used: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    @property
    def verification_status(self) -> str:
        """Verification status derived from email_verified, NOT is_active."""
        return "verified" if self.email_verified else "unverified"

    @property
    def scan_quota_override(self) -> int | None:
        """Scan quota overrides sourced from the official UserScanQuota relationship."""
        if self.scan_quota and self.scan_quota.override_mode == "custom":
            return self.scan_quota.custom_limit
        return None

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
    email_verifications: Mapped[list["EmailVerification"]] = relationship(
        "EmailVerification",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    collection_items: Mapped[list["CollectionItem"]] = relationship(
        "CollectionItem",
        back_populates="user",
    )
    scan_quota: Mapped["UserScanQuota | None"] = relationship(
        "UserScanQuota",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    scans: Mapped[list["Scan"]] = relationship(
        "Scan",
        back_populates="user",
    )
    beta_code_redemptions: Mapped[list["BetaCodeRedemption"]] = relationship(
        "BetaCodeRedemption",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    accepted_invitations: Mapped[list["Invitation"]] = relationship(
        "Invitation",
        foreign_keys="Invitation.accepted_by_user_id",
        back_populates="accepted_by_user",
    )


class EmailVerification(Base):
    """Email verification and email change tokens with cryptographic hashing."""

    __tablename__ = "email_verifications"
    __table_args__ = (
        Index("ix_email_verifications_user_id", "user_id"),
        Index("ix_email_verifications_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    token_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="email_verification",
        server_default="email_verification",
    )
    target_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )

    # Relationship
    user: Mapped["User"] = relationship(
        "User",
        back_populates="email_verifications",
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
