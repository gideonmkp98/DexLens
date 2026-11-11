"""Provisional migration for Phase 9 account security improvements.

Revision ID: 0015_phase9_provisional
Revises: 0014
Create Date: 2026-11-11 18:00:00.000000

Provisional dependency: revises 0014 (enforce_phase8_owner_uniqueness).
To be finalized and renumbered by the integration agent.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_phase9_provisional"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add Phase 9 columns to users table
    op.add_column("users", sa.Column("username", sa.String(length=50), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("policies_accepted_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("username_changed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    # 2. Create email_verifications table for hashed verification tokens
    op.create_table(
        "email_verifications",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "token_type",
            sa.String(length=32),
            nullable=False,
            server_default="email_verification",
        ),
        sa.Column("target_email", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_email_verifications_token_hash",
        "email_verifications",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_email_verifications_user_id",
        "email_verifications",
        ["user_id"],
    )
    op.create_index(
        "ix_email_verifications_expires_at",
        "email_verifications",
        ["expires_at"],
    )


def downgrade() -> None:
    # 1. Drop email_verifications table
    op.drop_table("email_verifications")

    # 2. Drop Phase 9 columns and indexes from users table
    op.drop_index("ix_users_username", table_name="users")
    op.drop_column("users", "username_changed_at")
    op.drop_column("users", "policies_accepted_at")
    op.drop_column("users", "email_verified")
    op.drop_column("users", "username")
