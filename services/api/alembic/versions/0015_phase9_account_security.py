"""Phase 9 migration: Account security, username normalization, and email verification.

Revision ID: 0015_phase9_account_security
Revises: 0014
Create Date: 2026-11-11 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0015_phase9_account_security"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    existing_tables = set(insp.get_table_names())

    # 1. Add Phase 9 Account Security columns to users table
    if "users" in existing_tables:
        existing_cols = {c["name"] for c in insp.get_columns("users")}
        if "username" not in existing_cols:
            op.add_column(
                "users", sa.Column("username", sa.String(length=50), nullable=True)
            )
            op.create_index("ix_users_username", "users", ["username"], unique=True)
        if "email_verified" not in existing_cols:
            op.add_column(
                "users",
                sa.Column(
                    "email_verified",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("0"),
                ),
            )
        if "policies_accepted_at" not in existing_cols:
            op.add_column(
                "users",
                sa.Column("policies_accepted_at", sa.DateTime(), nullable=True),
            )
        if "username_changed_at" not in existing_cols:
            op.add_column(
                "users",
                sa.Column("username_changed_at", sa.DateTime(), nullable=True),
            )

    # 2. Create email_verifications table for hashed verification tokens
    if "email_verifications" not in existing_tables:
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
    bind = op.get_bind()
    insp = inspect(bind)
    existing_tables = set(insp.get_table_names())

    # 1. Drop email_verifications table
    if "email_verifications" in existing_tables:
        op.drop_table("email_verifications")

    # 2. Drop Phase 9 Account Security columns and indexes from users table
    if "users" in existing_tables:
        existing_cols = {c["name"] for c in insp.get_columns("users")}
        existing_indexes = {ix["name"] for ix in insp.get_indexes("users")}

        if "ix_users_username" in existing_indexes:
            op.drop_index("ix_users_username", table_name="users")
        if "username_changed_at" in existing_cols:
            op.drop_column("users", "username_changed_at")
        if "policies_accepted_at" in existing_cols:
            op.drop_column("users", "policies_accepted_at")
        if "email_verified" in existing_cols:
            op.drop_column("users", "email_verified")
        if "username" in existing_cols:
            op.drop_column("users", "username")
