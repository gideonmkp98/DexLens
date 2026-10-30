"""Link multiple scans to grouped collection items.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-30 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collection_scan_links",
        sa.Column("scan_id", sa.String(length=36), nullable=False),
        sa.Column("collection_item_id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["scan_id"],
            ["scans.id"],
            name="fk_collection_scan_links_scan_id_scans",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["collection_item_id"],
            ["collection_items.id"],
            name="fk_collection_scan_links_item_id_collection_items",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("scan_id", name="pk_collection_scan_links"),
    )
    op.create_index(
        "ix_collection_scan_links_collection_item_id",
        "collection_scan_links",
        ["collection_item_id"],
        unique=False,
    )

    # Preserve idempotency for collection items created before this migration.
    op.execute(
        sa.text(
            """
            INSERT INTO collection_scan_links (scan_id, collection_item_id)
            SELECT source_scan_id, id
            FROM collection_items
            WHERE source_scan_id IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_table("collection_scan_links")
