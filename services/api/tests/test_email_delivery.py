import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.integrations.email import (
    InMemoryEmailProvider,
    ResendEmailProvider,
    SmtpEmailProvider,
    get_email_provider,
    override_email_provider,
)


@pytest.fixture(autouse=True)
def reset_email_provider():
    override_email_provider(None)
    yield
    override_email_provider(None)


def test_registration_dispatches_verification_email(client: TestClient):
    provider = InMemoryEmailProvider()
    override_email_provider(provider)
    email = f"email-delivery-{uuid.uuid4().hex[:8]}@example.com"

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "UniqueEmailDeliveryPassword2026!",
        },
    )

    assert response.status_code == 201
    messages = provider.get_messages_for_email(email)
    assert len(messages) == 1
    assert messages[0]["type"] == "email_verification"
    assert messages[0]["verification_url"].startswith(
        f"{settings.EMAIL_PUBLIC_BASE_URL}/verify-email?token="
    )


def test_resend_dispatches_new_verification_email(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    provider = InMemoryEmailProvider()
    override_email_provider(provider)
    email = f"email-resend-{uuid.uuid4().hex[:8]}@example.com"
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "UniqueEmailResendPassword2026!",
        },
    )
    assert registration.status_code == 201
    provider.clear()
    monkeypatch.setattr(settings, "EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS", 0)

    response = client.post(
        "/api/v1/auth/resend-verification",
        json={"email": email},
    )

    assert response.status_code == 200
    messages = provider.get_messages_for_email(email)
    assert len(messages) == 1
    assert messages[0]["type"] == "email_verification"


def test_resend_provider_sends_verification_without_logging_token(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    token = "secret-verification-token"
    response = MagicMock()
    response.raise_for_status.return_value = None
    post = MagicMock(return_value=response)
    monkeypatch.setattr("app.integrations.email.httpx.post", post)
    provider = ResendEmailProvider("re_test_key")

    assert provider.send_verification(
        "collector@example.com",
        token,
        datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=24),
    )
    payload = post.call_args.kwargs["json"]
    assert token in payload["text"]
    assert token not in caplog.text


def test_provider_factory_supports_production_adapters(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test_key")
    assert isinstance(get_email_provider(), ResendEmailProvider)

    override_email_provider(None)
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "smtp")
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    assert isinstance(get_email_provider(), SmtpEmailProvider)
