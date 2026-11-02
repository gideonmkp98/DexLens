"""Add Phase 8 auth, analytics, scan feedback, and ownership fields.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-02 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _drop_foreign_key_for_columns(table_name: str, columns: list[str]) -> None:
    """Drop the matching FK regardless of MariaDB's assigned constraint name."""
    inspector = inspect(op.get_bind())
    for foreign_key in inspector.get_foreign_keys(table_name):
        if foreign_key.get("constrained_columns") == columns:
            name = foreign_key.get("name")
            if name:
                op.drop_constraint(name, table_name, type_="foreignkey")
                return


def upgrade() -> None:
    # 1. Users table
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="user"),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
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
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # 2. User sessions table
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column(
            "session_type",
            sa.String(length=16),
            nullable=False,
            server_default="anonymous",
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
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
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_user_sessions_session_token_hash",
        "user_sessions",
        ["session_token_hash"],
        unique=True,
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])
    op.create_foreign_key(
        "fk_user_sessions_user_id_users",
        "user_sessions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 3. Product analytics events table
    op.create_table(
        "product_analytics_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("event_name", sa.String(length=64), nullable=False),
        sa.Column(
            "schema_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("scan_id", sa.String(length=36), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("capture_mode", sa.String(length=16), nullable=True),
        sa.Column("device_category", sa.String(length=32), nullable=True),
        sa.Column("browser_category", sa.String(length=32), nullable=True),
        sa.Column("viewport_category", sa.String(length=16), nullable=True),
        sa.Column("processing_duration_ms", sa.Integer(), nullable=True),
        sa.Column("confidence_state", sa.String(length=16), nullable=True),
        sa.Column("candidate_count", sa.Integer(), nullable=True),
        sa.Column("is_top_suggestion_selected", sa.Boolean(), nullable=True),
        sa.Column("failure_category", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_pae_event_name_timestamp",
        "product_analytics_events",
        ["event_name", "timestamp"],
    )
    op.create_index("ix_pae_actor_id", "product_analytics_events", ["actor_id"])
    op.create_index("ix_pae_session_id", "product_analytics_events", ["session_id"])
    op.create_index("ix_pae_scan_id", "product_analytics_events", ["scan_id"])
    op.create_index("ix_pae_timestamp", "product_analytics_events", ["timestamp"])
    op.create_index("ix_pae_created_at", "product_analytics_events", ["created_at"])

    # 4. Scan feedback table
    op.create_table(
        "scan_feedback",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("scan_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("anonymous_session_id", sa.String(length=36), nullable=True),
        sa.Column("feedback_type", sa.String(length=32), nullable=False),
        sa.Column("suggested_card_id", sa.String(length=100), nullable=True),
        sa.Column("selected_card_id", sa.String(length=100), nullable=True),
        sa.Column("confidence_state", sa.String(length=16), nullable=True),
        sa.Column("selected_in_candidates", sa.Boolean(), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("device_category", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_scan_feedback_scan_id", "scan_feedback", ["scan_id"])
    op.create_index("ix_scan_feedback_user_id", "scan_feedback", ["user_id"])
    op.create_index(
        "ix_scan_feedback_anonymous_session_id",
        "scan_feedback",
        ["anonymous_session_id"],
    )
    op.create_index("ix_scan_feedback_created_at", "scan_feedback", ["created_at"])
    op.create_foreign_key(
        "fk_scan_feedback_scan_id_scans",
        "scan_feedback",
        "scans",
        ["scan_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_scan_feedback_user_id_users",
        "scan_feedback",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 5. Extend collection_items
    op.add_column(
        "collection_items",
        sa.Column("user_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "collection_items",
        sa.Column("anonymous_session_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_collection_items_user_id",
        "collection_items",
        ["user_id"],
    )
    op.create_index(
        "ix_collection_items_anonymous_session_id",
        "collection_items",
        ["anonymous_session_id"],
    )
    op.create_foreign_key(
        "fk_collection_items_user_id_users",
        "collection_items",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "uq_collection_items_grouping",
        "collection_items",
        type_="unique",
    )
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

    # 6. Extend scans
    op.add_column(
        "scans",
        sa.Column("user_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column("anonymous_session_id", sa.String(length=36), nullable=True),
    )
    op.create_index("ix_scans_user_id", "scans", ["user_id"])
    op.create_index(
        "ix_scans_anonymous_session_id",
        "scans",
        ["anonymous_session_id"],
    )
    op.create_foreign_key(
        "fk_scans_user_id_users",
        "scans",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 7. Extend scan_sessions
    op.add_column(
        "scan_sessions",
        sa.Column("user_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "scan_sessions",
        sa.Column("anonymous_session_id", sa.String(length=36), nullable=True),
    )
    op.create_index("ix_scan_sessions_user_id", "scan_sessions", ["user_id"])
    op.create_index(
        "ix_scan_sessions_anonymous_session_id",
        "scan_sessions",
        ["anonymous_session_id"],
    )
    op.create_foreign_key(
        "fk_scan_sessions_user_id_users",
        "scan_sessions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # 7. Revert scan_sessions
    _drop_foreign_key_for_columns("scan_sessions", ["user_id"])
    op.drop_index("ix_scan_sessions_anonymous_session_id", table_name="scan_sessions")
    op.drop_index("ix_scan_sessions_user_id", table_name="scan_sessions")
    op.drop_column("scan_sessions", "anonymous_session_id")
    op.drop_column("scan_sessions", "user_id")

    # 6. Revert scans
    _drop_foreign_key_for_columns("scans", ["user_id"])
    op.drop_index("ix_scans_anonymous_session_id", table_name="scans")
    op.drop_index("ix_scans_user_id", table_name="scans")
    op.drop_column("scans", "anonymous_session_id")
    op.drop_column("scans", "user_id")

    # 5. Revert collection_items
    op.drop_constraint(
        "uq_collection_items_grouping",
        "collection_items",
        type_="unique",
    )
    _drop_foreign_key_for_columns("collection_items", ["user_id"])
    op.drop_index(
        "ix_collection_items_anonymous_session_id", table_name="collection_items"
    )
    op.drop_index("ix_collection_items_user_id", table_name="collection_items")
    op.drop_column("collection_items", "anonymous_session_id")
    op.drop_column("collection_items", "user_id")
    op.create_unique_constraint(
        "uq_collection_items_grouping",
        "collection_items",
        ["provider", "card_id", "language", "variant", "condition"],
    )

    # 4. Drop scan_feedback
    _drop_foreign_key_for_columns("scan_feedback", ["user_id"])
    _drop_foreign_key_for_columns("scan_feedback", ["scan_id"])
    op.drop_index("ix_scan_feedback_created_at", table_name="scan_feedback")
    op.drop_index("ix_scan_feedback_anonymous_session_id", table_name="scan_feedback")
    op.drop_index("ix_scan_feedback_user_id", table_name="scan_feedback")
    op.drop_index("ix_scan_feedback_scan_id", table_name="scan_feedback")
    op.drop_table("scan_feedback")

    # 3. Drop product_analytics_events
    op.drop_index("ix_pae_created_at", table_name="product_analytics_events")
    op.drop_index("ix_pae_timestamp", table_name="product_analytics_events")
    op.drop_index("ix_pae_scan_id", table_name="product_analytics_events")
    op.drop_index("ix_pae_session_id", table_name="product_analytics_events")
    op.drop_index("ix_pae_actor_id", table_name="product_analytics_events")
    op.drop_index("ix_pae_event_name_timestamp", table_name="product_analytics_events")
    op.drop_table("product_analytics_events")

    # 2. Drop user_sessions
    _drop_foreign_key_for_columns("user_sessions", ["user_id"])
    op.drop_index("ix_user_sessions_expires_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_index("ix_user_sessions_session_token_hash", table_name="user_sessions")
    op.drop_table("user_sessions")

    # 1. Drop users
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
