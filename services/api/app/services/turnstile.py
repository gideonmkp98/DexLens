import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import Request

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TurnstileVerificationResult:
    """Result of Turnstile token verification."""

    success: bool
    error_code: str | None = None
    error_message: str | None = None
    action: str | None = None
    hostname: str | None = None
    challenge_ts: str | None = None


class TurnstileService:
    """Cloudflare Turnstile managed verification service.

    Handles token replay protection, trusted proxy IP resolution,
    secure live Cloudflare Siteverify calls, and explicit test-mode behavior.
    """

    _used_tokens: dict[str, float] = {}
    _lock = threading.Lock()

    @classmethod
    def get_trusted_client_ip(cls, request: Request) -> str:
        """Extract client IP, using forwarded header only from trusted proxies."""
        peer_ip = request.client.host if request.client else "127.0.0.1"
        x_forwarded = request.headers.get("x-forwarded-for")

        trusted_proxies = (
            set(settings.TRUSTED_PROXY_IPS)
            if isinstance(settings.TRUSTED_PROXY_IPS, list)
            else set()
        )

        if x_forwarded and peer_ip in trusted_proxies:
            ips = [ip.strip() for ip in x_forwarded.split(",") if ip.strip()]
            if ips:
                return ips[0]

        return peer_ip

    @classmethod
    def hash_token(cls, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @classmethod
    def _is_token_replayed(cls, token: str) -> bool:
        """Check if token hash was previously consumed and record it if fresh."""
        token_hash = cls.hash_token(token)
        now = time.time()
        ttl = settings.TURNSTILE_TOKEN_TTL_SECONDS

        with cls._lock:
            # Purge expired hashes
            expired = [
                h for h, expire_at in cls._used_tokens.items() if expire_at <= now
            ]
            for h in expired:
                del cls._used_tokens[h]

            if token_hash in cls._used_tokens:
                return True

            cls._used_tokens[token_hash] = now + ttl
            return False

    @classmethod
    def reset_replay_cache(cls) -> None:
        """Reset replay tracking cache (used in test suites)."""
        with cls._lock:
            cls._used_tokens.clear()

    @classmethod
    def verify(
        cls,
        token: str,
        expected_action: str | None = None,
        client_ip: str | None = None,
    ) -> TurnstileVerificationResult:
        """Verify Turnstile token against Cloudflare Siteverify.

        In production, tokens are strictly sent to Cloudflare Siteverify.
        Local test-token handling exists ONLY when:
        1. Environment is explicitly 'test' or 'development'
        2. settings.TURNSTILE_TEST_MODE is True
        """
        if not token or not token.strip():
            return TurnstileVerificationResult(
                success=False,
                error_code="MISSING_TOKEN",
                error_message="Veiligheidscontrole ontbreekt.",
            )

        token = token.strip()
        token_hash_prefix = cls.hash_token(token)[:8]

        # 1. Check single-use replay protection
        if cls._is_token_replayed(token):
            logger.warning(
                "Turnstile token replay detected (hash_prefix=%s)",
                token_hash_prefix,
            )
            return TurnstileVerificationResult(
                success=False,
                error_code="TOKEN_REPLAYED",
                error_message=(
                    "Deze verificatiecode is al gebruikt. Vernieuw de controle."
                ),
            )

        # 2. Check if local test mode is explicitly enabled and allowed
        is_dev_or_test_env = settings.ENVIRONMENT.lower() in {
            "test",
            "development",
            "dev",
        }
        is_test_mode_allowed = (
            is_dev_or_test_env
            and settings.TURNSTILE_TEST_MODE
            and settings.ENVIRONMENT.lower() not in {"production", "prod"}
        )

        if is_test_mode_allowed:
            # Dedicated explicit test-mode evaluation
            if (
                token
                in (
                    "test-fail-token",
                    "XXXX.DUMMY.FAIL",
                    "2x0000000000000000000000000000000AB",
                )
                or "fail" in token
            ):
                return TurnstileVerificationResult(
                    success=False,
                    error_code="INVALID_TOKEN",
                    error_message="Veiligheidscontrole mislukt. Probeer het opnieuw.",
                )
            if token == "test-expired-token":
                return TurnstileVerificationResult(
                    success=False,
                    error_code="TOKEN_EXPIRED",
                    error_message=(
                        "Veiligheidscontrole is verlopen. Probeer het opnieuw."
                    ),
                )
            if token == "test-action-mismatch":
                return TurnstileVerificationResult(
                    success=False,
                    error_code="ACTION_MISMATCH",
                    error_message="Verificatie-actie komt niet overeen.",
                )
            if (
                expected_action
                and token.startswith("test-action-")
                and token != f"test-action-{expected_action}"
            ):
                return TurnstileVerificationResult(
                    success=False,
                    error_code="ACTION_MISMATCH",
                    error_message="Verificatie-actie komt niet overeen.",
                )
            return TurnstileVerificationResult(
                success=True,
                action=expected_action,
                hostname=settings.TURNSTILE_EXPECTED_HOSTNAME or "localhost",
            )

        # In production or when test mode disabled, live Siteverify is mandatory.
        if not settings.TURNSTILE_SECRET_KEY:
            logger.error("Turnstile verification invoked without configured secret key")
            return TurnstileVerificationResult(
                success=False,
                error_code="VERIFY_SERVICE_UNAVAILABLE",
                error_message="Verificatiedienst is niet geconfigureerd.",
            )

        payload: dict[str, Any] = {
            "secret": settings.TURNSTILE_SECRET_KEY,
            "response": token,
        }
        if client_ip:
            payload["remoteip"] = client_ip

        try:
            with httpx.Client(timeout=5.0) as client:
                res = client.post(settings.TURNSTILE_VERIFY_URL, data=payload)
                if res.status_code != 200:
                    logger.warning(
                        "Turnstile siteverify returned HTTP %d for hash_prefix=%s",
                        res.status_code,
                        token_hash_prefix,
                    )
                    return TurnstileVerificationResult(
                        success=False,
                        error_code="VERIFY_SERVICE_UNAVAILABLE",
                        error_message="Verificatiedienst tijdelijk niet bereikbaar.",
                    )
                data = res.json()
        except httpx.TimeoutException:
            logger.warning(
                "Turnstile siteverify timed out after 5.0s for hash_prefix=%s",
                token_hash_prefix,
            )
            return TurnstileVerificationResult(
                success=False,
                error_code="VERIFY_TIMEOUT",
                error_message="Verificatiedienst time-out. Probeer het opnieuw.",
            )
        except Exception as exc:
            logger.warning(
                "Failed to connect to Turnstile siteverify (%s) for hash_prefix=%s",
                type(exc).__name__,
                token_hash_prefix,
            )
            return TurnstileVerificationResult(
                success=False,
                error_code="VERIFY_SERVICE_UNAVAILABLE",
                error_message="Verificatiedienst tijdelijk niet bereikbaar.",
            )

        if not data.get("success"):
            error_codes = data.get("error-codes", [])
            logger.info(
                "Turnstile verification rejected by Cloudflare for hash_prefix=%s: %s",
                token_hash_prefix,
                error_codes,
            )
            if "timeout-or-duplicate" in error_codes:
                return TurnstileVerificationResult(
                    success=False,
                    error_code="TOKEN_EXPIRED",
                    error_message="Veiligheidscontrole is verlopen of herhaald.",
                )
            return TurnstileVerificationResult(
                success=False,
                error_code="INVALID_TOKEN",
                error_message="Veiligheidscontrole is ongeldig.",
            )

        token_action = data.get("action")
        if expected_action and token_action and token_action != expected_action:
            logger.warning(
                "Turnstile action mismatch: expected '%s', received '%s'",
                expected_action,
                token_action,
            )
            return TurnstileVerificationResult(
                success=False,
                error_code="ACTION_MISMATCH",
                error_message="Verificatie-actie komt niet overeen.",
            )

        token_hostname = data.get("hostname")
        if (
            settings.TURNSTILE_EXPECTED_HOSTNAME
            and token_hostname
            and token_hostname != settings.TURNSTILE_EXPECTED_HOSTNAME
        ):
            logger.warning(
                "Turnstile hostname mismatch: expected '%s', received '%s'",
                settings.TURNSTILE_EXPECTED_HOSTNAME,
                token_hostname,
            )
            return TurnstileVerificationResult(
                success=False,
                error_code="HOSTNAME_MISMATCH",
                error_message="Verificatie-bronlocatie komt niet overeen.",
            )

        return TurnstileVerificationResult(
            success=True,
            action=token_action,
            hostname=token_hostname,
            challenge_ts=data.get("challenge_ts"),
        )
