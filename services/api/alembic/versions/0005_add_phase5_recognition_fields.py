"""Add scan recognition, candidate matching, and card confirmation fields for Phase 5

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-26 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scans",
        sa.Column(
            "recognition_status",
            sa.String(length=32),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        "scans",
        sa.Column("recognition_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column("ocr_crop_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column("ocr_raw_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column("recognized_name", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column("recognized_number", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column("recognized_set_code", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column(
            "search_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "scans",
        sa.Column("candidate_matches", sa.JSON(), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column("confirmed_card_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column("confirmed_card_name", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column("confirmed_card_set_name", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column("confirmed_card_number", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column("confirmed_card_image_url", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column("card_confirmed_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scans", "card_confirmed_at")
    op.drop_column("scans", "confirmed_card_image_url")
    op.drop_column("scans", "confirmed_card_number")
    op.drop_column("scans", "confirmed_card_set_name")
    op.drop_column("scans", "confirmed_card_name")
    op.drop_column("scans", "confirmed_card_id")
    op.drop_column("scans", "candidate_matches")
    op.drop_column("scans", "search_version")
    op.drop_column("scans", "ocr_confidence")
    op.drop_column("scans", "recognized_set_code")
    op.drop_column("scans", "recognized_number")
    op.drop_column("scans", "recognized_name")
    op.drop_column("scans", "ocr_raw_text")
    op.drop_column("scans", "ocr_crop_version")
    op.drop_column("scans", "recognition_id")
    op.drop_column("scans", "recognition_status")
