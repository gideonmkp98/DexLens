"""Enforce owner-aware collection and feedback uniqueness.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-02 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OWNER_EXPRESSION = (
    "CASE "
    "WHEN user_id IS NOT NULL THEN CONCAT('user:', user_id) "
    "WHEN anonymous_session_id IS NOT NULL "
    "THEN CONCAT('anon:', anonymous_session_id) "
    "ELSE 'legacy' END"
)


def _deduplicate_collection_items() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, user_id, anonymous_session_id, provider, card_id,
                   language, variant, `condition`, quantity, version,
                   source_scan_id
            FROM collection_items
            ORDER BY created_at ASC, id ASC
            """
        )
    ).mappings()

    winners: dict[tuple[object, ...], dict[str, object]] = {}
    for row in rows:
        owner_key = (
            f"user:{row['user_id']}"
            if row["user_id"] is not None
            else (
                f"anon:{row['anonymous_session_id']}"
                if row["anonymous_session_id"] is not None
                else "legacy"
            )
        )
        key = (
            owner_key,
            row["provider"],
            row["card_id"],
            row["language"],
            row["variant"],
            row["condition"],
        )
        winner = winners.get(key)
        if winner is None:
            winners[key] = dict(row)
            continue

        winner_id = str(winner["id"])
        loser_id = str(row["id"])
        bind.execute(
            sa.text(
                """
                UPDATE collection_scan_links
                SET collection_item_id = :winner_id
                WHERE collection_item_id = :loser_id
                """
            ),
            {"winner_id": winner_id, "loser_id": loser_id},
        )
        new_quantity = int(winner["quantity"]) + int(row["quantity"])
        new_version = max(int(winner["version"]), int(row["version"])) + 1
        source_scan_id = winner["source_scan_id"] or row["source_scan_id"]
        bind.execute(
            sa.text(
                """
                UPDATE collection_items
                SET quantity = :quantity, version = :version,
                    source_scan_id = :source_scan_id
                WHERE id = :winner_id
                """
            ),
            {
                "quantity": new_quantity,
                "version": new_version,
                "source_scan_id": source_scan_id,
                "winner_id": winner_id,
            },
        )
        bind.execute(
            sa.text("DELETE FROM collection_items WHERE id = :loser_id"),
            {"loser_id": loser_id},
        )
        winner["quantity"] = new_quantity
        winner["version"] = new_version
        winner["source_scan_id"] = source_scan_id


def _deduplicate_feedback() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, scan_id, user_id, anonymous_session_id
            FROM scan_feedback
            ORDER BY created_at DESC, id DESC
            """
        )
    ).mappings()
    seen: set[tuple[str, str]] = set()
    for row in rows:
        owner_key = (
            f"user:{row['user_id']}"
            if row["user_id"] is not None
            else (
                f"anon:{row['anonymous_session_id']}"
                if row["anonymous_session_id"] is not None
                else "legacy"
            )
        )
        key = (str(row["scan_id"]), owner_key)
        if key in seen:
            bind.execute(
                sa.text("DELETE FROM scan_feedback WHERE id = :feedback_id"),
                {"feedback_id": row["id"]},
            )
        else:
            seen.add(key)


def _has_column(table_name: str, column_name: str) -> bool:
    return any(
        column["name"] == column_name
        for column in inspect(op.get_bind()).get_columns(table_name)
    )


def _has_unique(table_name: str, constraint_name: str) -> bool:
    return any(
        constraint.get("name") == constraint_name
        for constraint in inspect(op.get_bind()).get_unique_constraints(table_name)
    )


def _drop_foreign_key_for_columns(table_name: str, columns: list[str]) -> None:
    for foreign_key in inspect(op.get_bind()).get_foreign_keys(table_name):
        if foreign_key.get("constrained_columns") == columns:
            name = foreign_key.get("name")
            if name:
                op.drop_constraint(name, table_name, type_="foreignkey")
                return


def upgrade() -> None:
    _deduplicate_collection_items()
    _deduplicate_feedback()

    if _has_unique("collection_items", "uq_collection_items_grouping"):
        op.drop_constraint(
            "uq_collection_items_grouping", "collection_items", type_="unique"
        )
    if not _has_column("collection_items", "owner_key"):
        op.add_column(
            "collection_items",
            sa.Column(
                "owner_key",
                sa.String(length=41),
                sa.Computed(OWNER_EXPRESSION, persisted=True),
                nullable=True,
            ),
        )
    if not _has_unique("collection_items", "uq_collection_items_owner_grouping"):
        op.create_unique_constraint(
            "uq_collection_items_owner_grouping",
            "collection_items",
            [
                "owner_key",
                "provider",
                "card_id",
                "language",
                "variant",
                "condition",
            ],
        )

    # MariaDB disallows a generated column based on a FK column whose referential
    # action mutates that column. Deleting a user should delete their feedback,
    # which also avoids producing globally unowned privacy records.
    _drop_foreign_key_for_columns("scan_feedback", ["user_id"])
    op.create_foreign_key(
        "fk_scan_feedback_user_id_users",
        "scan_feedback",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    if not _has_column("scan_feedback", "owner_key"):
        op.add_column(
            "scan_feedback",
            sa.Column(
                "owner_key",
                sa.String(length=41),
                sa.Computed(OWNER_EXPRESSION, persisted=True),
                nullable=True,
            ),
        )
    if not _has_unique("scan_feedback", "uq_scan_feedback_scan_owner"):
        op.create_unique_constraint(
            "uq_scan_feedback_scan_owner",
            "scan_feedback",
            ["scan_id", "owner_key"],
        )


def downgrade() -> None:
    op.drop_constraint("uq_scan_feedback_scan_owner", "scan_feedback", type_="unique")
    op.drop_column("scan_feedback", "owner_key")
    _drop_foreign_key_for_columns("scan_feedback", ["user_id"])
    op.create_foreign_key(
        "fk_scan_feedback_user_id_users",
        "scan_feedback",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint(
        "uq_collection_items_owner_grouping",
        "collection_items",
        type_="unique",
    )
    op.drop_column("collection_items", "owner_key")
    op.create_unique_constraint(
        "uq_collection_items_grouping",
        "collection_items",
        [
            "user_id",
            "anonymous_session_id",
            "provider",
            "card_id",
            "language",
            "variant",
            "condition",
        ],
    )
