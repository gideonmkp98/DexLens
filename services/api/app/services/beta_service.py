"""Beta service interface and domain protocol.

Integration Contract for Integration Agent:
The administration subsystem consumes the `BetaServiceInterface` protocol.
When integrating the parallel `beta` branch, wire the concrete `BetaService`
implementation to `get_beta_service` via FastAPI dependency injection or
container setup.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class BetaCodeItem:
    """Read model for beta access codes and personalized invitations."""

    id: str
    code: str
    code_prefix: str
    label: str | None
    invitation_email: str | None
    max_uses: int
    used_count: int
    status: str
    expires_at: datetime | None
    created_at: datetime
    created_by_user_id: str | None


class BetaServiceInterface(Protocol):
    """Stable interface contract consumed by Admin and Auth for beta codes."""

    def list_codes(
        self,
        status: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[BetaCodeItem], int]:
        """List and search existing beta codes and invitations with pagination."""
        ...

    def create_code(
        self,
        code: str | None = None,
        label: str | None = None,
        invitation_email: str | None = None,
        max_uses: int = 1,
        expires_at: datetime | None = None,
        created_by_id: str | None = None,
    ) -> BetaCodeItem:
        """Provision a new beta code or single-use user invitation."""
        ...

    def revoke_code(
        self,
        code_or_id: str,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> BetaCodeItem:
        """Revoke an active beta code or invitation."""
        ...

    def claim_code(
        self,
        code: str,
        user_id: str,
        ip_hash: str | None = None,
    ) -> bool:
        """Redeem a beta code for an authenticated user."""
        ...
