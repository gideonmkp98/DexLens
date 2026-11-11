import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


def mask_token_for_log(token: str) -> str:
    """Mask sensitive tokens before emitting to general logs."""
    if not token or len(token) < 8:
        return "[REDACTED]"
    return f"{token[:4]}...[REDACTED]...{token[-4:]}"


class BaseEmailProvider(ABC):
    """Abstract interface for dispatching system and invitation emails."""

    @abstractmethod
    def send_invitation(
        self,
        to_email: str,
        invite_token: str,
        expires_at: datetime,
        invitation_id: str,
        beta_entitlement: str | None = None,
    ) -> bool:
        """Deliver a personal beta invitation to the target recipient."""
        raise NotImplementedError


class InMemoryEmailProvider(BaseEmailProvider):
    """Safe test and local development email provider.

    Retains messages in memory for test assertions without leaking secrets
    into external systems or disk logs.
    """

    def __init__(self) -> None:
        self.sent_messages: list[dict[str, Any]] = []

    def send_invitation(
        self,
        to_email: str,
        invite_token: str,
        expires_at: datetime,
        invitation_id: str,
        beta_entitlement: str | None = None,
    ) -> bool:
        norm_email = to_email.strip().lower()
        invite_url = f"/invite#token={invite_token}"
        message = {
            "to": norm_email,
            "invitation_id": invitation_id,
            "token": invite_token,  # Kept in-memory for unit test assertions
            "invite_url": invite_url,
            "expires_at": expires_at,
            "beta_entitlement": beta_entitlement,
            "sent_at": datetime.now(),
        }
        self.sent_messages.append(message)
        logger.info(
            "InMemoryEmailProvider: queued invitation for %s (id=%s, token=%s)",
            norm_email,
            invitation_id,
            mask_token_for_log(invite_token),
        )
        return True

    def get_sent_messages(self) -> list[dict[str, Any]]:
        return list(self.sent_messages)

    def get_messages_for_email(self, email: str) -> list[dict[str, Any]]:
        norm = email.strip().lower()
        return [msg for msg in self.sent_messages if msg["to"] == norm]

    def clear(self) -> None:
        self.sent_messages.clear()


class ConsoleEmailProvider(BaseEmailProvider):
    """Console provider for local development without external SMTP setup.

    Safe: Masks the raw token in log output to prevent leakage into log aggregators.
    """

    def send_invitation(
        self,
        to_email: str,
        invite_token: str,
        expires_at: datetime,
        invitation_id: str,
        beta_entitlement: str | None = None,
    ) -> bool:
        norm_email = to_email.strip().lower()
        logger.info(
            "ConsoleEmailProvider: [INVITATION] to=%s, id=%s, "
            "token_preview=%s, expires=%s",
            norm_email,
            invitation_id,
            mask_token_for_log(invite_token),
            expires_at.isoformat(),
        )
        return True


# Global default email provider instance
_default_email_provider: BaseEmailProvider | None = None


def get_email_provider() -> BaseEmailProvider:
    """Dependency resolver for application email provider."""
    global _default_email_provider
    if _default_email_provider is not None:
        return _default_email_provider

    provider_name = settings.EMAIL_PROVIDER.lower().strip()
    if provider_name == "console":
        _default_email_provider = ConsoleEmailProvider()
    else:
        _default_email_provider = InMemoryEmailProvider()

    return _default_email_provider


def override_email_provider(provider: BaseEmailProvider | None) -> None:
    """Helper to set or reset mock email providers during testing."""
    global _default_email_provider
    _default_email_provider = provider
