"""Compatibility marker for the provisional Phase 9 admin migration.

Revision ID: 0015_provisional
Revises: 0014

Some development databases applied the temporary Antigravity migration before
the final Phase 9 migration chain was merged. The original migration added the
``users.status`` column and ``admin_audit_logs`` table. Both are created
idempotently by the definitive ``0018`` migration, so this retained revision is
intentionally a no-op. Keeping the revision in the graph lets Alembic advance
those databases without rewriting migration history or dropping data.
"""

from collections.abc import Sequence

revision: str = "0015_provisional"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
