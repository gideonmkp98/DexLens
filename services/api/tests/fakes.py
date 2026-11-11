"""Test fakes for external subsystem interfaces (Beta and Quota).

These test fakes implement the BetaServiceInterface and QuotaServiceInterface protocols
so that admin API and abuse protection tests run deterministically without creating
competing production domain logic.
"""

import uuid
from datetime import UTC, datetime

from app.services.beta_service import BetaCodeItem, BetaServiceInterface
from app.services.quota_service import (
    GlobalQuotaSettings,
    QuotaServiceInterface,
    UserQuotaOverview,
)


class FakeBetaService(BetaServiceInterface):
    """In-memory test fake implementing BetaServiceInterface."""

    def __init__(self) -> None:
        self.codes: dict[str, BetaCodeItem] = {}

    def list_codes(
        self,
        status: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[BetaCodeItem], int]:
        # Return unique items (dictionary has both id and code keys)
        unique_items = {item.id: item for item in self.codes.values()}
        items = list(unique_items.values())
        if status:
            items = [c for c in items if c.status == status]
        if search:
            s = search.lower()
            items = [
                c
                for c in items
                if s in c.code.lower() or (c.label and s in c.label.lower())
            ]
        total = len(items)
        return items[offset : offset + limit], total

    def create_code(
        self,
        code: str | None = None,
        label: str | None = None,
        invitation_email: str | None = None,
        max_uses: int = 1,
        expires_at: datetime | None = None,
        created_by_id: str | None = None,
    ) -> BetaCodeItem:
        code_str = code or f"BETA-{uuid.uuid4().hex[:8].upper()}"
        item = BetaCodeItem(
            id=str(uuid.uuid4()),
            code=code_str,
            code_prefix=code_str[:4],
            label=label,
            invitation_email=invitation_email,
            max_uses=max_uses,
            used_count=0,
            status="active",
            expires_at=expires_at,
            created_at=datetime.now(UTC).replace(tzinfo=None),
            created_by_user_id=created_by_id,
        )
        self.codes[item.id] = item
        self.codes[item.code] = item
        return item

    def revoke_code(
        self,
        code_or_id: str,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> BetaCodeItem:
        item = self.codes.get(code_or_id)
        if not item:
            for c in self.codes.values():
                if c.id == code_or_id or c.code == code_or_id:
                    item = c
                    break
        if not item:
            raise KeyError(f"Beta code not found: {code_or_id}")
        item.status = "revoked"
        return item

    def claim_code(
        self,
        code: str,
        user_id: str,
        ip_hash: str | None = None,
    ) -> bool:
        item = self.codes.get(code)
        if not item:
            for c in self.codes.values():
                if c.code == code:
                    item = c
                    break
        if not item or item.status != "active":
            return False
        if item.used_count >= item.max_uses:
            return False
        item.used_count += 1
        if item.used_count >= item.max_uses:
            item.status = "exhausted"
        return True


class FakeQuotaService(QuotaServiceInterface):
    """In-memory test fake implementing QuotaServiceInterface."""

    def __init__(self, daily_limit: int = 100, hourly_limit: int = 30) -> None:
        self.global_settings = GlobalQuotaSettings(
            daily_scan_limit=daily_limit,
            hourly_scan_limit=hourly_limit,
            updated_at=datetime.now(UTC).replace(tzinfo=None),
        )
        self.user_overrides: dict[str, int | None] = {}
        self.user_usage: dict[str, int] = {}

    def get_global_quota(self) -> GlobalQuotaSettings:
        return self.global_settings

    def update_global_quota(
        self,
        daily_limit: int,
        hourly_limit: int,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> GlobalQuotaSettings:
        self.global_settings.daily_scan_limit = daily_limit
        self.global_settings.hourly_scan_limit = hourly_limit
        self.global_settings.updated_at = datetime.now(UTC).replace(tzinfo=None)
        return self.global_settings

    def get_user_quota(self, user_id: str) -> UserQuotaOverview:
        override = self.user_overrides.get(user_id)
        effective = (
            override if override is not None else self.global_settings.daily_scan_limit
        )
        used = self.user_usage.get(user_id, 0)
        return UserQuotaOverview(
            user_id=user_id,
            email=f"user_{user_id}@example.com",
            effective_daily_limit=effective,
            custom_override=override,
            reason="Test override" if override else None,
            scans_used_today=used,
            remaining_today=max(0, effective - used),
        )

    def set_user_quota_override(
        self,
        user_id: str,
        custom_limit: int | None,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> UserQuotaOverview:
        self.user_overrides[user_id] = custom_limit
        return self.get_user_quota(user_id)
