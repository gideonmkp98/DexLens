"""Add scan crop and perspective fields for Phase 4

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-25 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scans",
        sa.Column(
            "crop_status",
            sa.String(length=32),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        "scans",
        sa.Column("corners", sa.JSON(), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column(
            "rotation",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "scans",
        sa.Column("crop_path", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column("crop_width", sa.Integer(), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column("crop_height", sa.Integer(), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column("crop_file_size", sa.Integer(), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column(
            "crop_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "scans",
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scans", "confirmed_at")
    op.drop_column("scans", "crop_version")
    op.drop_column("scans", "crop_file_size")
    op.drop_column("scans", "crop_height")
    op.drop_column("scans", "crop_width")
    op.drop_column("scans", "crop_path")
    op.drop_column("scans", "rotation")
    op.drop_column("scans", "corners")
    op.drop_column("scans", "crop_status")
