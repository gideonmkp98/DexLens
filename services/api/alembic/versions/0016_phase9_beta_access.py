"""Phase 9 migration: Beta access, codes, and personal invitations.

Revision ID: 0016_phase9_beta_access
Revises: 0015_phase9_account_security
Create Date: 2026-11-11 18:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0016_phase9_beta_access"
down_revision: str | None = "0015_phase9_account_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    existing_tables = set(insp.get_table_names())

    # 1. Add Beta Access columns to users table
    if "users" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("users")}
        if "has_beta_access" not in existing_cols:
            op.add_column(
                "users",
                sa.Column(
                    "has_beta_access",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("0"),
                ),
            )
        if "beta_entitlement" not in existing_cols:
            op.add_column(
                "users",
                sa.Column("beta_entitlement", sa.String(length=64), nullable=True),
            )
        if "registration_mode_used" not in existing_cols:
            op.add_column(
                "users",
                sa.Column(
                    "registration_mode_used",
                    sa.String(length=32),
                    nullable=True,
                ),
            )

    # 2. app_settings table
    if "app_settings" not in existing_tables:
        op.create_table(
            "app_settings",
            sa.Column("key", sa.String(length=64), primary_key=True),
            sa.Column("value", sa.String(length=255), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    # 3. beta_codes table
    if "beta_codes" not in existing_tables:
        op.create_table(
            "beta_codes",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("code_hash", sa.String(length=64), nullable=False),
            sa.Column("code_prefix", sa.String(length=16), nullable=False),
            sa.Column("label", sa.String(length=100), nullable=False),
            sa.Column("allowed_email", sa.String(length=255), nullable=True),
            sa.Column("beta_entitlement", sa.String(length=64), nullable=True),
            sa.Column("scan_quota_allocated", sa.Integer(), nullable=True),
            sa.Column("max_uses", sa.Integer(), nullable=True),
            sa.Column(
                "used_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1"),
            ),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column(
                "created_by_user_id",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "revoked_by_user_id",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index(
            "ix_beta_codes_code_hash", "beta_codes", ["code_hash"], unique=True
        )
        op.create_index("ix_beta_codes_code_prefix", "beta_codes", ["code_prefix"])
        op.create_index("ix_beta_codes_is_active", "beta_codes", ["is_active"])
        op.create_index("ix_beta_codes_expires_at", "beta_codes", ["expires_at"])

    # 4. beta_code_redemptions table
    if "beta_code_redemptions" not in existing_tables:
        op.create_table(
            "beta_code_redemptions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "beta_code_id",
                sa.String(length=36),
                sa.ForeignKey("beta_codes.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "user_id",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "redeemed_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("ip_hash", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=255), nullable=True),
            sa.UniqueConstraint(
                "beta_code_id", "user_id", name="uq_beta_code_user_redemption"
            ),
        )
        op.create_index(
            "ix_beta_code_redemptions_beta_code_id",
            "beta_code_redemptions",
            ["beta_code_id"],
        )
        op.create_index(
            "ix_beta_code_redemptions_user_id",
            "beta_code_redemptions",
            ["user_id"],
        )

    # 5. invitations table
    if "invitations" not in existing_tables:
        op.create_table(
            "invitations",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("beta_entitlement", sa.String(length=64), nullable=True),
            sa.Column("scan_quota_allocated", sa.Integer(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column(
                "sent_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "resend_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column("accepted_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column(
                "accepted_by_user_id",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_by_user_id",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "revoked_by_user_id",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index(
            "ix_invitations_token_hash", "invitations", ["token_hash"], unique=True
        )
        op.create_index("ix_invitations_email", "invitations", ["email"])
        op.create_index(
            "ix_invitations_email_status", "invitations", ["email", "status"]
        )
        op.create_index("ix_invitations_expires_at", "invitations", ["expires_at"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "invitations" in existing_tables:
        op.drop_table("invitations")

    if "beta_code_redemptions" in existing_tables:
        op.drop_table("beta_code_redemptions")

    if "beta_codes" in existing_tables:
        op.drop_table("beta_codes")

    if "app_settings" in existing_tables:
        op.drop_table("app_settings")

    if "users" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("users")}
        if "registration_mode_used" in existing_cols:
            op.drop_column("users", "registration_mode_used")
        if "beta_entitlement" in existing_cols:
            op.drop_column("users", "beta_entitlement")
        if "has_beta_access" in existing_cols:
            op.drop_column("users", "has_beta_access")
