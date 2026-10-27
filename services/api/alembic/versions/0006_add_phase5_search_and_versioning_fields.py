"""Add Phase 5 user search persistence, catalog status, and card selection versioning

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-26 18:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scans",
        sa.Column(
            "card_selection_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "scans",
        sa.Column(
            "catalog_status",
            sa.String(length=32),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        "scans",
        sa.Column("catalog_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column("user_search_name", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column("user_search_number", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column("user_search_set_code", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column("user_search_provider_set_id", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scans", "user_search_provider_set_id")
    op.drop_column("scans", "user_search_set_code")
    op.drop_column("scans", "user_search_number")
    op.drop_column("scans", "user_search_name")
    op.drop_column("scans", "catalog_error")
    op.drop_column("scans", "catalog_status")
    op.drop_column("scans", "card_selection_version")
