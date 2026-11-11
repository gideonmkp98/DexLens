"""Phase 9 migration: Daily scan quotas and usage metering tables.

Revision ID: 0017_phase9_scan_quotas
Revises: 0016_phase9_beta_access
Create Date: 2026-11-11 18:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0017_phase9_scan_quotas"
down_revision: str | None = "0016_phase9_beta_access"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    existing_tables = set(insp.get_table_names())

    # 1. scan_quota_settings
    if "scan_quota_settings" not in existing_tables:
        op.create_table(
            "scan_quota_settings",
            sa.Column("key", sa.String(64), primary_key=True),
            sa.Column("value", sa.String(255), nullable=False),
            sa.Column("description", sa.String(255), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    # 2. user_scan_quotas
    if "user_scan_quotas" not in existing_tables:
        op.create_table(
            "user_scan_quotas",
            sa.Column(
                "user_id",
                sa.String(36),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(
                "override_mode",
                sa.String(32),
                nullable=False,
                server_default="inherit",
            ),
            sa.Column("custom_limit", sa.Integer(), nullable=True),
            sa.Column("reason", sa.String(255), nullable=True),
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

    # 3. daily_scan_usage
    if "daily_scan_usage" not in existing_tables:
        op.create_table(
            "daily_scan_usage",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("owner_key", sa.String(64), nullable=False),
            sa.Column(
                "user_id",
                sa.String(36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("anonymous_session_id", sa.String(36), nullable=True),
            sa.Column("usage_date", sa.Date(), nullable=False),
            sa.Column(
                "used_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
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
            sa.UniqueConstraint(
                "owner_key", "usage_date", name="uq_daily_scan_usage_owner_date"
            ),
        )
        op.create_index(
            "ix_daily_scan_usage_owner_key", "daily_scan_usage", ["owner_key"]
        )
        op.create_index(
            "ix_daily_scan_usage_usage_date", "daily_scan_usage", ["usage_date"]
        )
        op.create_index(
            "ix_daily_scan_usage_lookup",
            "daily_scan_usage",
            ["owner_key", "usage_date"],
        )
        op.create_index("ix_daily_scan_usage_user_id", "daily_scan_usage", ["user_id"])
        op.create_index(
            "ix_daily_scan_usage_anon_id",
            "daily_scan_usage",
            ["anonymous_session_id"],
        )

    # 4. scan_idempotency_records
    if "scan_idempotency_records" not in existing_tables:
        op.create_table(
            "scan_idempotency_records",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("owner_key", sa.String(64), nullable=False),
            sa.Column("idempotency_key", sa.String(64), nullable=False),
            sa.Column(
                "scan_id",
                sa.String(36),
                sa.ForeignKey("scans.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("usage_date", sa.Date(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint(
                "owner_key",
                "idempotency_key",
                name="uq_scan_idempotency_owner_key",
            ),
        )
        op.create_index(
            "ix_scan_idempotency_owner_key",
            "scan_idempotency_records",
            ["owner_key"],
        )
        op.create_index(
            "ix_scan_idempotency_scan_id",
            "scan_idempotency_records",
            ["scan_id"],
        )
        op.create_index(
            "ix_scan_idempotency_date",
            "scan_idempotency_records",
            ["usage_date"],
        )

    # 5. scans.upload_idempotency_key column
    if "scans" in existing_tables:
        scans_columns = {c["name"] for c in insp.get_columns("scans")}
        if "upload_idempotency_key" not in scans_columns:
            op.add_column(
                "scans",
                sa.Column("upload_idempotency_key", sa.String(64), nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "scans" in existing_tables:
        scans_columns = {c["name"] for c in insp.get_columns("scans")}
        if "upload_idempotency_key" in scans_columns:
            op.drop_column("scans", "upload_idempotency_key")

    if "scan_idempotency_records" in existing_tables:
        op.drop_table("scan_idempotency_records")

    if "daily_scan_usage" in existing_tables:
        op.drop_table("daily_scan_usage")

    if "user_scan_quotas" in existing_tables:
        op.drop_table("user_scan_quotas")

    if "scan_quota_settings" in existing_tables:
        op.drop_table("scan_quota_settings")
