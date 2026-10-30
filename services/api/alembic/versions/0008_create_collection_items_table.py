"""Create collection_items table for Phase 6 personal collection

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-30 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collection_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("card_id", sa.String(length=100), nullable=False),
        sa.Column(
            "provider",
            sa.String(length=32),
            nullable=False,
            server_default="tcgdex",
        ),
        sa.Column("card_name", sa.String(length=255), nullable=False),
        sa.Column("set_id", sa.String(length=50), nullable=False),
        sa.Column("set_name", sa.String(length=255), nullable=False),
        sa.Column("collector_number", sa.String(length=50), nullable=False),
        sa.Column("card_image_url", sa.String(length=512), nullable=True),
        sa.Column(
            "quantity",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "language",
            sa.String(length=10),
            nullable=False,
            server_default="en",
        ),
        sa.Column(
            "variant",
            sa.String(length=32),
            nullable=False,
            server_default="normal",
        ),
        sa.Column(
            "condition",
            sa.String(length=32),
            nullable=False,
            server_default="near_mint",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "purchase_price",
            sa.Numeric(precision=10, scale=2),
            nullable=True,
        ),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("acquired_at", sa.Date(), nullable=True),
        sa.Column("source_scan_id", sa.String(length=36), nullable=True),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default="1",
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
        sa.PrimaryKeyConstraint("id", name="pk_collection_items"),
        sa.ForeignKeyConstraint(
            ["source_scan_id"],
            ["scans.id"],
            ondelete="SET NULL",
            name="fk_collection_items_source_scan_id_scans",
        ),
        sa.CheckConstraint(
            "quantity >= 1",
            name="ck_collection_items_quantity_positive",
        ),
        sa.CheckConstraint(
            "purchase_price IS NULL OR purchase_price >= 0",
            name="ck_collection_items_purchase_price_non_negative",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_collection_items_version_positive",
        ),
    )

    # Single-column search, filtering, and sorting indexes
    op.create_index(
        op.f("ix_collection_items_card_id"),
        "collection_items",
        ["card_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_collection_items_card_name"),
        "collection_items",
        ["card_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_collection_items_set_id"),
        "collection_items",
        ["set_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_collection_items_language"),
        "collection_items",
        ["language"],
        unique=False,
    )
    op.create_index(
        op.f("ix_collection_items_variant"),
        "collection_items",
        ["variant"],
        unique=False,
    )
    op.create_index(
        op.f("ix_collection_items_condition"),
        "collection_items",
        ["condition"],
        unique=False,
    )
    op.create_index(
        op.f("ix_collection_items_source_scan_id"),
        "collection_items",
        ["source_scan_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_collection_items_created_at"),
        "collection_items",
        ["created_at"],
        unique=False,
    )

    # Composite indexes for set catalog filtering and duplicate/variant grouping
    op.create_index(
        "ix_collection_items_set_collector",
        "collection_items",
        ["set_id", "collector_number"],
        unique=False,
    )
    op.create_index(
        "ix_collection_items_card_variant_lang",
        "collection_items",
        ["card_id", "variant", "language"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("collection_items")
