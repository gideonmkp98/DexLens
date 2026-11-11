import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailProviderError(Exception):
    """Base exception for email provider errors."""


class ProductionEmailProviderNotConfiguredError(EmailProviderError):
    """Raised when an email is sent in production without a configured provider."""


class BaseEmailProvider(ABC):
    """Abstract interface for dispatching system and invitation emails.

    Integration Agent Note:
    To connect a real transactional email provider (e.g. Resend, SendGrid, SES):
    1. Subclass BaseEmailProvider.
    2. Implement `send_invitation` using the provider's SDK or REST API.
    3. Register the provider in `get_email_provider()` keyed to
       `settings.EMAIL_PROVIDER` (e.g. 'resend', 'ses').
    4. Provide the required provider API key / SMTP configuration via env vars.
    """

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
        if settings.ENVIRONMENT.lower() in {"production", "prod"}:
            raise ProductionEmailProviderNotConfiguredError(
                "InMemoryEmailProvider cannot be used in production environments."
            )
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
            "InMemoryEmailProvider: queued invitation for %s (id=%s)",
            norm_email,
            invitation_id,
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

    Safe: Never logs raw or masked tokens. Only logs recipient and invitation ID.
    """

    def send_invitation(
        self,
        to_email: str,
        invite_token: str,
        expires_at: datetime,
        invitation_id: str,
        beta_entitlement: str | None = None,
    ) -> bool:
        if settings.ENVIRONMENT.lower() in {"production", "prod"}:
            raise ProductionEmailProviderNotConfiguredError(
                "ConsoleEmailProvider cannot be used in production environments."
            )
        norm_email = to_email.strip().lower()
        logger.info(
            "ConsoleEmailProvider: [INVITATION] to=%s, id=%s, expires=%s",
            norm_email,
            invitation_id,
            expires_at.isoformat(),
        )
        return True


class UnavailableEmailProvider(BaseEmailProvider):
    """Fallback provider when no valid provider is configured for the environment."""

    def send_invitation(
        self,
        to_email: str,
        invite_token: str,
        expires_at: datetime,
        invitation_id: str,
        beta_entitlement: str | None = None,
    ) -> bool:
        raise ProductionEmailProviderNotConfiguredError(
            "No production email provider has been configured. "
            "Please configure a valid email delivery service."
        )


# Global default email provider instance
_default_email_provider: BaseEmailProvider | None = None


def get_email_provider() -> BaseEmailProvider:
    """Dependency resolver for application email provider."""
    global _default_email_provider
    if _default_email_provider is not None:
        return _default_email_provider

    provider_name = settings.EMAIL_PROVIDER.lower().strip()
    is_prod = settings.ENVIRONMENT.lower() in {"production", "prod"}

    if is_prod and provider_name in {"memory", "console"}:
        _default_email_provider = UnavailableEmailProvider()
    elif provider_name == "console":
        _default_email_provider = ConsoleEmailProvider()
    elif provider_name == "memory":
        _default_email_provider = InMemoryEmailProvider()
    else:
        _default_email_provider = UnavailableEmailProvider()

    return _default_email_provider


def override_email_provider(provider: BaseEmailProvider | None) -> None:
    """Helper to set or reset mock email providers during testing."""
    global _default_email_provider
    _default_email_provider = provider
