import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
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


class BetaCode(Base):
    """Beta access registration code with atomic usage tracking and restrictions."""

    __tablename__ = "beta_codes"
    __table_args__ = (
        Index("ix_beta_codes_code_hash", "code_hash", unique=True),
        Index("ix_beta_codes_code_prefix", "code_prefix"),
        Index("ix_beta_codes_is_active", "is_active"),
        Index("ix_beta_codes_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    code_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )
    code_prefix: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
    )
    label: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
    )
    max_uses: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    used_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    allowed_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    scan_quota_allocated: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    beta_entitlement: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoked_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
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

    # Relationships
    redemptions: Mapped[list["BetaCodeRedemption"]] = relationship(
        "BetaCodeRedemption",
        back_populates="beta_code",
        cascade="all, delete-orphan",
    )
    created_by: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[created_by_user_id],
    )
    revoked_by: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[revoked_by_user_id],
    )


class BetaCodeRedemption(Base):
    """Audit log of beta code redemptions by registered users."""

    __tablename__ = "beta_code_redemptions"
    __table_args__ = (
        UniqueConstraint(
            "beta_code_id", "user_id", name="uq_beta_code_user_redemption"
        ),
        Index("ix_beta_code_redemptions_beta_code_id", "beta_code_id"),
        Index("ix_beta_code_redemptions_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    beta_code_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("beta_codes.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    redeemed_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
    ip_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Relationships
    beta_code: Mapped["BetaCode"] = relationship(
        "BetaCode",
        back_populates="redemptions",
    )
    user: Mapped["User"] = relationship(
        "User",
        back_populates="beta_code_redemptions",
    )


class Invitation(Base):
    """Personal email invitation record with single-use hashed token and lifecycle."""

    __tablename__ = "invitations"
    __table_args__ = (
        Index("ix_invitations_token_hash", "token_hash", unique=True),
        Index("ix_invitations_email_status", "email", "status"),
        Index("ix_invitations_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )  # "pending", "accepted", "revoked", "expired"
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
    resend_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    scan_quota_allocated: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    beta_entitlement: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    accepted_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoked_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
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

    # Relationships
    created_by: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[created_by_user_id],
    )
    accepted_by_user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[accepted_by_user_id],
        back_populates="accepted_invitations",
    )
    revoked_by: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[revoked_by_user_id],
    )
