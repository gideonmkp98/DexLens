"""Enforce database grouping unique constraint on collection items.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-30 22:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Safely merge any pre-existing duplicate items sharing the grouping identity
    # (provider, card_id, language, variant, condition)
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT provider, card_id, language, variant, `condition`, COUNT(*) as cnt
            FROM collection_items
            GROUP BY provider, card_id, language, variant, `condition`
            HAVING cnt > 1
            """
        )
    ).fetchall()

    for row in rows:
        provider = row[0]
        card_id = row[1]
        language = row[2]
        variant = row[3]
        condition = row[4]

        # Fetch all matching items ordered by created_at asc
        items = bind.execute(
            sa.text(
                """
                SELECT id, quantity, version
                FROM collection_items
                WHERE provider = :provider
                  AND card_id = :card_id
                  AND language = :language
                  AND variant = :variant
                  AND `condition` = :condition
                ORDER BY created_at ASC, id ASC
                """
            ),
            {
                "provider": provider,
                "card_id": card_id,
                "language": language,
                "variant": variant,
                "condition": condition,
            },
        ).fetchall()

        if len(items) > 1:
            primary_id = items[0][0]
            total_qty = sum(item[1] for item in items)
            other_ids = [item[0] for item in items[1:]]

            # Re-point scan links from duplicate items to the primary item
            for other_id in other_ids:
                bind.execute(
                    sa.text(
                        """
                        UPDATE collection_scan_links
                        SET collection_item_id = :primary_id
                        WHERE collection_item_id = :other_id
                        """
                    ),
                    {"primary_id": primary_id, "other_id": other_id},
                )
                # Delete the redundant item
                bind.execute(
                    sa.text("DELETE FROM collection_items WHERE id = :other_id"),
                    {"other_id": other_id},
                )

            # Update primary item's quantity and version
            bind.execute(
                sa.text(
                    """
                    UPDATE collection_items
                    SET quantity = :total_qty, version = version + 1
                    WHERE id = :primary_id
                    """
                ),
                {"total_qty": total_qty, "primary_id": primary_id},
            )

    # 2. Add the unique constraint enforcing grouping at the database level
    op.create_unique_constraint(
        "uq_collection_items_grouping",
        "collection_items",
        ["provider", "card_id", "language", "variant", "condition"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_collection_items_grouping",
        "collection_items",
        type_="unique",
    )
