"""Add idempotency key for live scan captures.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scans",
        sa.Column("capture_idempotency_key", sa.String(length=64), nullable=True),
    )
    op.create_unique_constraint(
        "uq_scans_session_capture_key",
        "scans",
        ["session_id", "capture_idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_scans_session_capture_key",
        "scans",
        type_="unique",
    )
    op.drop_column("scans", "capture_idempotency_key")
