"""Merge the provisional Phase 9 branch into the definitive migration chain.

Revision ID: 0019_merge_phase9_provisional
Revises: 0018_phase9_admin_audit_status, 0015_provisional
"""

from collections.abc import Sequence

revision: str = "0019_merge_phase9_provisional"
down_revision: tuple[str, str] = (
    "0018_phase9_admin_audit_status",
    "0015_provisional",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
