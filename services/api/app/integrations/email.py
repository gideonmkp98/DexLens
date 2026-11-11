import logging
import smtplib
from abc import ABC, abstractmethod
from datetime import datetime
from email.message import EmailMessage
from html import escape
from typing import Any
from urllib.parse import quote

import httpx

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

    @abstractmethod
    def send_verification(
        self,
        to_email: str,
        verification_token: str,
        expires_at: datetime,
    ) -> bool:
        """Deliver an account verification link to the target recipient."""
        raise NotImplementedError


def _public_url(path: str) -> str:
    return f"{settings.EMAIL_PUBLIC_BASE_URL.rstrip('/')}{path}"


def _invitation_url(token: str) -> str:
    return _public_url(f"/invite#token={quote(token, safe='')}")


def _verification_url(token: str) -> str:
    return _public_url(f"/verify-email?token={quote(token, safe='')}")


def _invitation_content(expires_at: datetime) -> tuple[str, str]:
    subject = "Je DexLens-uitnodiging"
    text = (
        "Je bent uitgenodigd voor DexLens. Open de link om je account af te maken. "
        f"De uitnodiging verloopt op {expires_at.isoformat()}."
    )
    return subject, text


def _verification_content(expires_at: datetime) -> tuple[str, str]:
    subject = "Bevestig je DexLens e-mailadres"
    text = (
        "Bevestig je e-mailadres om je DexLens-account te activeren. "
        f"De link verloopt op {expires_at.isoformat()}."
    )
    return subject, text


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
        invite_url = _invitation_url(invite_token)
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

    def send_verification(
        self,
        to_email: str,
        verification_token: str,
        expires_at: datetime,
    ) -> bool:
        if settings.ENVIRONMENT.lower() in {"production", "prod"}:
            raise ProductionEmailProviderNotConfiguredError(
                "InMemoryEmailProvider cannot be used in production environments."
            )
        norm_email = to_email.strip().lower()
        self.sent_messages.append(
            {
                "to": norm_email,
                "type": "email_verification",
                "token": verification_token,
                "verification_url": _verification_url(verification_token),
                "expires_at": expires_at,
                "sent_at": datetime.now(),
            }
        )
        logger.info("Queued email verification for %s", norm_email)
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

    def send_verification(
        self,
        to_email: str,
        verification_token: str,
        expires_at: datetime,
    ) -> bool:
        if settings.ENVIRONMENT.lower() in {"production", "prod"}:
            raise ProductionEmailProviderNotConfiguredError(
                "ConsoleEmailProvider cannot be used in production environments."
            )
        logger.info(
            "ConsoleEmailProvider: [VERIFICATION] to=%s, expires=%s",
            to_email.strip().lower(),
            expires_at.isoformat(),
        )
        return True


class ResendEmailProvider(BaseEmailProvider):
    """Transactional delivery through the Resend HTTPS API."""

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ProductionEmailProviderNotConfiguredError(
                "RESEND_API_KEY is required for the Resend provider."
            )
        self.api_key = api_key

    def _send(self, to_email: str, subject: str, text: str, url: str) -> bool:
        safe_url = escape(url, quote=True)
        html = (
            f"<p>{escape(text)}</p>"
            f'<p><a href="{safe_url}">Open DexLens</a></p>'
            "<p>Heb je dit niet aangevraagd? Dan kun je deze e-mail negeren.</p>"
        )
        try:
            response = httpx.post(
                settings.RESEND_API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": settings.EMAIL_FROM,
                    "to": [to_email.strip().lower()],
                    "subject": subject,
                    "text": f"{text}\n\n{url}",
                    "html": html,
                },
                timeout=settings.EMAIL_DELIVERY_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EmailProviderError("Resend email delivery failed") from exc
        return True

    def send_invitation(
        self,
        to_email: str,
        invite_token: str,
        expires_at: datetime,
        invitation_id: str,
        beta_entitlement: str | None = None,
    ) -> bool:
        subject, text = _invitation_content(expires_at)
        return self._send(to_email, subject, text, _invitation_url(invite_token))

    def send_verification(
        self,
        to_email: str,
        verification_token: str,
        expires_at: datetime,
    ) -> bool:
        subject, text = _verification_content(expires_at)
        return self._send(
            to_email,
            subject,
            text,
            _verification_url(verification_token),
        )


class SmtpEmailProvider(BaseEmailProvider):
    """Transactional delivery through an authenticated SMTP server."""

    def _send(self, to_email: str, subject: str, text: str, url: str) -> bool:
        if not settings.SMTP_HOST:
            raise ProductionEmailProviderNotConfiguredError(
                "SMTP_HOST is required for the SMTP provider."
            )
        message = EmailMessage()
        message["From"] = settings.EMAIL_FROM
        message["To"] = to_email.strip().lower()
        message["Subject"] = subject
        message.set_content(f"{text}\n\n{url}")
        try:
            with smtplib.SMTP(
                settings.SMTP_HOST,
                settings.SMTP_PORT,
                timeout=settings.EMAIL_DELIVERY_TIMEOUT_SECONDS,
            ) as smtp:
                if settings.SMTP_USE_TLS:
                    smtp.starttls()
                if settings.SMTP_USERNAME:
                    smtp.login(
                        settings.SMTP_USERNAME,
                        settings.SMTP_PASSWORD or "",
                    )
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailProviderError("SMTP email delivery failed") from exc
        return True

    def send_invitation(
        self,
        to_email: str,
        invite_token: str,
        expires_at: datetime,
        invitation_id: str,
        beta_entitlement: str | None = None,
    ) -> bool:
        subject, text = _invitation_content(expires_at)
        return self._send(to_email, subject, text, _invitation_url(invite_token))

    def send_verification(
        self,
        to_email: str,
        verification_token: str,
        expires_at: datetime,
    ) -> bool:
        subject, text = _verification_content(expires_at)
        return self._send(
            to_email,
            subject,
            text,
            _verification_url(verification_token),
        )


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

    def send_verification(
        self,
        to_email: str,
        verification_token: str,
        expires_at: datetime,
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
    elif provider_name == "resend":
        _default_email_provider = ResendEmailProvider(settings.RESEND_API_KEY or "")
    elif provider_name == "smtp":
        _default_email_provider = SmtpEmailProvider()
    else:
        _default_email_provider = UnavailableEmailProvider()

    return _default_email_provider


def override_email_provider(provider: BaseEmailProvider | None) -> None:
    """Helper to set or reset mock email providers during testing."""
    global _default_email_provider
    _default_email_provider = provider
