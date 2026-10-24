"""Add Phase 2 catalog tables and extend sets

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-24 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add new columns to sets table as nullable initially to permit safe
    # backfilling of existing rows
    op.add_column(
        "sets",
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=True,
            server_default="tcgdex",
        ),
    )
    op.add_column(
        "sets",
        sa.Column("external_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "sets",
        sa.Column(
            "language",
            sa.String(length=10),
            nullable=True,
            server_default="en",
        ),
    )
    op.add_column(
        "sets",
        sa.Column("series", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "sets",
        sa.Column("logo_url", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "sets",
        sa.Column("symbol_url", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "sets",
        sa.Column("release_date", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "sets",
        sa.Column("printed_total", sa.Integer(), nullable=True),
    )
    op.add_column(
        "sets",
        sa.Column("total", sa.Integer(), nullable=True),
    )

    # 2. Compatibility strategy for existing rows:
    # assign 'legacy' source and deterministic 'legacy-<id>' external_id
    sets_table = sa.table(
        "sets",
        sa.column("id", sa.Integer),
        sa.column("source", sa.String),
        sa.column("external_id", sa.String),
        sa.column("language", sa.String),
    )
    op.execute(
        sets_table.update()
        .where(sets_table.c.external_id.is_(None))
        .values(
            source="legacy",
            external_id=sa.func.concat("legacy-", sets_table.c.id),
            language="en",
        )
    )

    # 3. Alter required columns to NOT NULL with appropriate server defaults
    op.alter_column(
        "sets",
        "source",
        existing_type=sa.String(length=32),
        nullable=False,
        server_default="tcgdex",
    )
    op.alter_column(
        "sets",
        "external_id",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.alter_column(
        "sets",
        "language",
        existing_type=sa.String(length=10),
        nullable=False,
        server_default="en",
    )

    # 4. Create unique constraint and index on sets
    op.create_index(op.f("ix_sets_external_id"), "sets", ["external_id"], unique=False)
    op.create_unique_constraint(
        "uq_sets_source_external_lang",
        "sets",
        ["source", "external_id", "language"],
    )

    # 5. Create cards table
    op.create_table(
        "cards",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default="tcgdex",
        ),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("set_id", sa.Integer(), nullable=False),
        sa.Column("local_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "language",
            sa.String(length=10),
            nullable=False,
            server_default="en",
        ),
        sa.Column("image_base_url", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["set_id"], ["sets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source", "external_id", "language", name="uq_cards_source_external_lang"
        ),
    )
    op.create_index(
        op.f("ix_cards_external_id"), "cards", ["external_id"], unique=False
    )
    op.create_index(op.f("ix_cards_set_id"), "cards", ["set_id"], unique=False)
    op.create_index(op.f("ix_cards_local_id"), "cards", ["local_id"], unique=False)
    op.create_index(op.f("ix_cards_name"), "cards", ["name"], unique=False)
    op.create_index("ix_cards_set_local", "cards", ["set_id", "local_id"], unique=False)

    # 6. Create import_runs table
    op.create_table(
        "import_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default="tcgdex",
        ),
        sa.Column(
            "language",
            sa.String(length=10),
            nullable=False,
            server_default="en",
        ),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_import_runs_started_at"),
        "import_runs",
        ["started_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_import_runs_status"), "import_runs", ["status"], unique=False
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS import_runs")
    op.execute("DROP TABLE IF EXISTS cards")

    try:
        op.drop_constraint("uq_sets_source_external_lang", "sets", type_="unique")
    except Exception:
        pass

    try:
        op.drop_index(op.f("ix_sets_external_id"), table_name="sets")
    except Exception:
        pass

    for col in [
        "total",
        "printed_total",
        "release_date",
        "symbol_url",
        "logo_url",
        "series",
        "language",
        "external_id",
        "source",
    ]:
        try:
            op.drop_column("sets", col)
        except Exception:
            pass
