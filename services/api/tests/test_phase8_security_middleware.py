import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.core.middleware import RateLimitMiddleware


def test_api_security_headers_are_present(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code in (200, 503)
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_general_rate_limit_does_not_trust_unconfigured_forwarded_ip(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "GENERAL_API_RATE_LIMIT_PER_MINUTE", 2)
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", [])
    RateLimitMiddleware.reset()

    first = client.get("/api/v1/auth/me", headers={"X-Forwarded-For": "198.51.100.1"})
    second = client.get("/api/v1/auth/me", headers={"X-Forwarded-For": "198.51.100.2"})
    blocked = client.get("/api/v1/auth/me", headers={"X-Forwarded-For": "198.51.100.3"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "RATE_LIMIT_EXCEEDED"


def test_production_configuration_fails_closed_with_insecure_defaults():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECURE_COOKIES=False,
            PILOT_ADMIN_SECRET="pilot-secret-dev",
        )


def test_production_configuration_accepts_explicit_secure_values():
    production_settings = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        SECURE_COOKIES=True,
        PILOT_ADMIN_SECRET="a-unique-production-secret-with-32-chars",
    )
    assert production_settings.SECURE_COOKIES is True
