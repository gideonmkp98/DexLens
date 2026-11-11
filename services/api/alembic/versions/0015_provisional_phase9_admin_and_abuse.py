"""Phase 9 provisional migration: admin audit logging and user account status.

Revision ID: 0015_provisional
Revises: 0014
Create Date: 2026-11-11 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_provisional"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Extend users table with administrative status column
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_user_cols = {c["name"] for c in insp.get_columns("users")}

    if "status" not in existing_user_cols:
        op.add_column(
            "users",
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default="active",
            ),
        )
        op.create_index("ix_users_status", "users", ["status"])

    # 2. Create append-only admin_audit_logs table
    existing_tables = set(insp.get_table_names())
    if "admin_audit_logs" not in existing_tables:
        op.create_table(
            "admin_audit_logs",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column(
                "actor_id",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("actor_email", sa.String(length=255), nullable=True),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("target_type", sa.String(length=64), nullable=False),
            sa.Column("target_id", sa.String(length=255), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("ip_hash", sa.String(length=64), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index(
            "ix_admin_audit_logs_actor_id", "admin_audit_logs", ["actor_id"]
        )
        op.create_index("ix_admin_audit_logs_action", "admin_audit_logs", ["action"])
        op.create_index(
            "ix_admin_audit_logs_target",
            "admin_audit_logs",
            ["target_type", "target_id"],
        )
        op.create_index(
            "ix_admin_audit_logs_created_at", "admin_audit_logs", ["created_at"]
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    if "admin_audit_logs" in existing_tables:
        op.drop_table("admin_audit_logs")

    if "users" in existing_tables:
        existing_user_cols = {c["name"] for c in insp.get_columns("users")}
        existing_indexes = {ix["name"] for ix in insp.get_indexes("users")}
        if "ix_users_status" in existing_indexes:
            op.drop_index("ix_users_status", table_name="users")
        if "status" in existing_user_cols:
            op.drop_column("users", "status")
        # Clean up legacy provisional columns if left behind
        if "scan_quota_override" in existing_user_cols:
            op.drop_column("users", "scan_quota_override")
        if "verification_status" in existing_user_cols:
            op.drop_column("users", "verification_status")
