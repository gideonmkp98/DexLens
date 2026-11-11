"""Provisional Phase 9 migration: Beta access, codes, and personal invitations.

PROVISIONAL MIGRATION NOTICE:
- Revision identifier: 'phase9_provisional'
- Depends on: '0014'
- The integration agent will assign the final linear migration number.

Revision ID: phase9_provisional
Revises: 0014
Create Date: 2026-11-11 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "phase9_provisional"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # 1. Add Phase 9 columns to users table if not already present
    if "users" in existing_tables:
        existing_user_cols = {col["name"] for col in inspector.get_columns("users")}
        if "has_beta_access" not in existing_user_cols:
            op.add_column(
                "users",
                sa.Column(
                    "has_beta_access",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("0"),
                ),
            )
        if "beta_entitlement" not in existing_user_cols:
            op.add_column(
                "users",
                sa.Column("beta_entitlement", sa.String(length=64), nullable=True),
            )
        if "scan_quota" not in existing_user_cols:
            op.add_column(
                "users",
                sa.Column("scan_quota", sa.Integer(), nullable=True),
            )
        if "registration_mode_used" not in existing_user_cols:
            op.add_column(
                "users",
                sa.Column(
                    "registration_mode_used", sa.String(length=32), nullable=True
                ),
            )

    # 2. Create beta_codes table
    if "beta_codes" not in existing_tables:
        op.create_table(
            "beta_codes",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("code_hash", sa.String(length=64), nullable=False),
            sa.Column("code_prefix", sa.String(length=12), nullable=False),
            sa.Column("label", sa.String(length=100), nullable=False),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1"),
            ),
            sa.Column("max_uses", sa.Integer(), nullable=True),
            sa.Column(
                "used_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column("allowed_email", sa.String(length=255), nullable=True),
            sa.Column("scan_quota_allocated", sa.Integer(), nullable=True),
            sa.Column("beta_entitlement", sa.String(length=64), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
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
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
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
        op.create_index(
            "ix_beta_codes_code_prefix", "beta_codes", ["code_prefix"], unique=False
        )
        op.create_index(
            "ix_beta_codes_is_active", "beta_codes", ["is_active"], unique=False
        )
        op.create_index(
            "ix_beta_codes_expires_at", "beta_codes", ["expires_at"], unique=False
        )

    # 3. Create beta_code_redemptions table
    if "beta_code_redemptions" not in existing_tables:
        op.create_table(
            "beta_code_redemptions",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
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
            unique=False,
        )
        op.create_index(
            "ix_beta_code_redemptions_user_id",
            "beta_code_redemptions",
            ["user_id"],
            unique=False,
        )

    # 4. Create invitations table
    if "invitations" not in existing_tables:
        op.create_table(
            "invitations",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="pending",
            ),
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
            sa.Column("scan_quota_allocated", sa.Integer(), nullable=True),
            sa.Column("beta_entitlement", sa.String(length=64), nullable=True),
            sa.Column(
                "created_by_user_id",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "accepted_by_user_id",
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
            sa.Column("accepted_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
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
        op.create_index(
            "ix_invitations_email_status",
            "invitations",
            ["email", "status"],
            unique=False,
        )
        op.create_index(
            "ix_invitations_expires_at", "invitations", ["expires_at"], unique=False
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "invitations" in existing_tables:
        op.drop_table("invitations")
    if "beta_code_redemptions" in existing_tables:
        op.drop_table("beta_code_redemptions")
    if "beta_codes" in existing_tables:
        op.drop_table("beta_codes")

    if "users" in existing_tables:
        existing_user_cols = {col["name"] for col in inspector.get_columns("users")}
        for col in [
            "registration_mode_used",
            "scan_quota",
            "beta_entitlement",
            "has_beta_access",
        ]:
            if col in existing_user_cols:
                op.drop_column("users", col)
