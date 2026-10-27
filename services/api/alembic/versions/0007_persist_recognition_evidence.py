"""Preserve OCR field confidence and source regions across reloads."""

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scans", sa.Column("recognition_evidence", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("scans", "recognition_evidence")
