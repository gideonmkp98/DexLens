"""Create scan_sessions table and link to scans

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-31 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create scan_sessions table
    op.create_table(
        "scan_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="active",
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
        sa.Column(
            "completed_at",
            sa.DateTime(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_scan_sessions"),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'abandoned')",
            name="ck_scan_sessions_status",
        ),
    )

    op.create_index(
        op.f("ix_scan_sessions_status_created_at"),
        "scan_sessions",
        ["status", "created_at"],
        unique=False,
    )

    # 2. Add session_id to scans table
    op.add_column(
        "scans",
        sa.Column("session_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        op.f("ix_scans_session_id"),
        "scans",
        ["session_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_scans_session_id_scan_sessions",
        "scans",
        "scan_sessions",
        ["session_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Safely locate the foreign key constraint name on scans.session_id in MariaDB/MySQL
    bind = op.get_bind()
    fk_name = "fk_scans_session_id_scan_sessions"
    try:
        found_fk = bind.execute(
            sa.text(
                "SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'scans' "
                "AND COLUMN_NAME = 'session_id' "
                "AND REFERENCED_TABLE_NAME = 'scan_sessions'"
            )
        ).scalar()
        if found_fk:
            fk_name = str(found_fk)
    except Exception:
        pass

    try:
        op.drop_constraint(
            fk_name,
            "scans",
            type_="foreignkey",
        )
    except Exception:
        pass

    try:
        op.drop_index(op.f("ix_scans_session_id"), table_name="scans")
    except Exception:
        pass

    op.drop_column("scans", "session_id")

    op.drop_index(
        op.f("ix_scan_sessions_status_created_at"),
        table_name="scan_sessions",
    )
    op.drop_table("scan_sessions")
