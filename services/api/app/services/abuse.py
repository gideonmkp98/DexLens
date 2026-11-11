import logging
import threading
import time
from typing import Any

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.services.turnstile import TurnstileService, TurnstileVerificationResult

logger = logging.getLogger(__name__)


class ScanChallengeRequiredError(HTTPException):
    """Raised when adaptive abuse detection requires Turnstile verification."""

    def __init__(
        self,
        site_key: str,
        message: str = "Veiligheidscontrole vereist. Los de verificatie op om door te gaan.",
        error_code: str = "CHALLENGE_REQUIRED",
    ) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": error_code,
                "message": message,
                "site_key": site_key,
                "action": "scan",
            },
            headers={"X-Challenge-Required": "turnstile"},
        )


class ScanRateLimitExceededError(HTTPException):
    """Raised when hard rate limits are exceeded independently of Turnstile."""

    def __init__(
        self,
        message: str = "Scan-limiet overschreden. Wacht even voordat je opnieuw scant.",
        retry_after: int = 60,
    ) -> None:
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "RATE_LIMIT_EXCEEDED",
                "message": message,
            },
            headers={"Retry-After": str(retry_after)},
        )


class ScanAbuseService:
    """Adaptive protection engine for image uploads and live scan sessions."""

    _burst_windows: dict[str, list[float]] = {}
    _rate_windows: dict[str, list[float]] = {}
    _lock = threading.Lock()

    @classmethod
    def reset(cls) -> None:
        """Reset internal windows (used in test suites)."""
        with cls._lock:
            cls._burst_windows.clear()
            cls._rate_windows.clear()

    @classmethod
    def _clean_window(cls, window: list[float], cutoff: float) -> list[float]:
        return [ts for ts in window if ts > cutoff]

    @classmethod
    def get_client_identifier(cls, request: Request, user_id: str | None = None) -> str:
        """Derive client identifier, prioritizing authenticated user ID over trusted IP."""
        if user_id:
            return f"user:{user_id}"
        ip = TurnstileService.get_trusted_client_ip(request)
        return f"ip:{ip}"

    @classmethod
    def check_and_record_scan(
        cls,
        request: Request,
        user_id: str | None = None,
        turnstile_token: str | None = None,
    ) -> None:
        """Evaluate adaptive abuse protection on incoming scan request.

        1. Enforces hard independent rate limit ceiling.
        2. Authenticated users scan with low friction.
        3. Anonymous or bursty traffic triggers Cloudflare Turnstile challenge.
        """
        now = time.time()
        client_ip = TurnstileService.get_trusted_client_ip(request)
        rate_key = f"rate:{client_ip}"
        burst_key = cls.get_client_identifier(request, user_id)

        with cls._lock:
            # 1. Independent hard rate limit check (per IP, 60s sliding window)
            rate_window = cls._clean_window(
                cls._rate_windows.get(rate_key, []),
                cutoff=now - 60.0,
            )
            if len(rate_window) >= settings.SCAN_HARD_RATE_LIMIT_PER_MINUTE:
                cls._rate_windows[rate_key] = rate_window
                logger.warning(
                    "Hard scan rate limit exceeded for %s (%d requests)",
                    rate_key,
                    len(rate_window),
                )
                raise ScanRateLimitExceededError(retry_after=60)

            # 2. Burst analysis for adaptive challenge
            burst_window = cls._clean_window(
                cls._burst_windows.get(burst_key, []),
                cutoff=now - settings.SCAN_BURST_WINDOW_SECONDS,
            )

            is_authenticated = user_id is not None
            threshold = (
                settings.SCAN_BURST_THRESHOLD * 4
                if is_authenticated
                else settings.SCAN_BURST_THRESHOLD
            )
            is_bursting = len(burst_window) >= threshold

            # Normal authenticated traffic without extreme burst bypasses Turnstile challenge
            if is_authenticated and not is_bursting:
                burst_window.append(now)
                rate_window.append(now)
                cls._burst_windows[burst_key] = burst_window
                cls._rate_windows[rate_key] = rate_window
                return

            # Normal anonymous traffic within low friction threshold bypasses challenge
            if not is_authenticated and not is_bursting:
                burst_window.append(now)
                rate_window.append(now)
                cls._burst_windows[burst_key] = burst_window
                cls._rate_windows[rate_key] = rate_window
                return

        # If here, challenge is required
        if not turnstile_token or not turnstile_token.strip():
            logger.info("Adaptive scan challenge triggered for %s (burst=%d)", burst_key, len(burst_window))
            raise ScanChallengeRequiredError(
                site_key=settings.TURNSTILE_SITE_KEY,
                message="Verdachte scanfrequentie gedetecteerd. Los de veiligheidscontrole op.",
            )

        # Validate provided token
        result = TurnstileService.verify(
            token=turnstile_token,
            expected_action="scan",
            client_ip=client_ip,
        )

        if not result.success:
            logger.warning(
                "Turnstile challenge validation failed for %s: %s",
                burst_key,
                result.error_code,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": result.error_code or "CHALLENGE_FAILED",
                    "message": result.error_message or "Veiligheidscontrole mislukt.",
                    "site_key": settings.TURNSTILE_SITE_KEY,
                },
                headers={"X-Challenge-Required": "turnstile"},
            )

        # Challenge passed! Reset the burst counter to allow smooth continuing scans
        with cls._lock:
            cls._burst_windows[burst_key] = []
            rate_window.append(now)
            cls._rate_windows[rate_key] = rate_window
        logger.info("Adaptive challenge successfully solved for %s", burst_key)
