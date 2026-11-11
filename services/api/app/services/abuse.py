import logging
import threading
import time
from typing import Protocol

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.services.turnstile import TurnstileService

logger = logging.getLogger(__name__)


class ScanChallengeRequiredError(HTTPException):
    """Raised when adaptive abuse detection requires Turnstile verification."""

    def __init__(
        self,
        site_key: str,
        message: str = (
            "Veiligheidscontrole vereist. Los de verificatie op om door te gaan."
        ),
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


class LimiterStorage(Protocol):
    """Storage backend protocol for rate limiter and burst tracking."""

    def get_count(self, key: str, window_seconds: float, now: float) -> int: ...

    def record_hit(self, key: str, now: float) -> None: ...

    def clear_key(self, key: str) -> None: ...

    def reset_all(self) -> None: ...


class InMemoryLimiterStorage:
    """Thread-safe in-memory sliding-window limiter storage.

    Architecture Note:
    InMemoryLimiterStorage provides process-local rate limiting within a single
    worker process. In a multi-worker production deployment, an injectable
    shared storage (e.g. RedisLimiterStorage) should be passed to enforce
    cross-worker rate limits.
    """

    def __init__(self) -> None:
        self._windows: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _clean(self, key: str, cutoff: float) -> list[float]:
        window = [ts for ts in self._windows.get(key, []) if ts > cutoff]
        self._windows[key] = window
        return window

    def get_count(self, key: str, window_seconds: float, now: float) -> int:
        with self._lock:
            return len(self._clean(key, now - window_seconds))

    def record_hit(self, key: str, now: float) -> None:
        with self._lock:
            if key not in self._windows:
                self._windows[key] = []
            self._windows[key].append(now)

    def clear_key(self, key: str) -> None:
        with self._lock:
            self._windows.pop(key, None)

    def reset_all(self) -> None:
        with self._lock:
            self._windows.clear()


class ScanAbuseService:
    """Adaptive protection engine for image uploads and live scan sessions.

    Separates permission checking from activity recording so invalid
    uploads or failed requests do not consume rate limit quotas.
    """

    storage: LimiterStorage = InMemoryLimiterStorage()

    @classmethod
    def set_storage(cls, storage: LimiterStorage) -> None:
        """Inject custom limiter storage backend (e.g. Redis or test fake)."""
        cls.storage = storage

    @classmethod
    def reset(cls) -> None:
        """Reset internal windows (used between tests)."""
        cls.storage.reset_all()

    @classmethod
    def get_client_identifier(cls, request: Request, user_id: str | None = None) -> str:
        """Derive client identifier, prioritizing user ID over trusted IP."""
        if user_id:
            return f"user:{user_id}"
        ip = TurnstileService.get_trusted_client_ip(request)
        return f"ip:{ip}"

    @classmethod
    def check_scan_permission(
        cls,
        request: Request,
        user_id: str | None = None,
        turnstile_token: str | None = None,
    ) -> None:
        """Check whether incoming scan request is permitted before processing image.

        Does NOT increment scan counts yet, ensuring invalid uploads
        do not corrupt limiter state.
        """
        now = time.time()
        client_ip = TurnstileService.get_trusted_client_ip(request)
        rate_key = f"rate:{client_ip}"
        burst_key = f"burst:{cls.get_client_identifier(request, user_id)}"

        # 1. Check independent hard rate limit ceiling (60s sliding window)
        rate_count = cls.storage.get_count(rate_key, 60.0, now)
        if rate_count >= settings.SCAN_HARD_RATE_LIMIT_PER_MINUTE:
            logger.warning(
                "Hard scan rate limit exceeded for %s (%d requests)",
                rate_key,
                rate_count,
            )
            raise ScanRateLimitExceededError(retry_after=60)

        # 2. Check burst window for adaptive challenge
        burst_count = cls.storage.get_count(
            burst_key, float(settings.SCAN_BURST_WINDOW_SECONDS), now
        )
        is_authenticated = user_id is not None
        threshold = (
            settings.SCAN_BURST_THRESHOLD * 4
            if is_authenticated
            else settings.SCAN_BURST_THRESHOLD
        )

        is_bursting = burst_count >= threshold

        # Within low friction threshold: allowed
        if not is_bursting:
            return

        # Burst threshold exceeded: challenge required if Turnstile is enabled
        if not settings.TURNSTILE_ENABLED and not settings.TURNSTILE_TEST_MODE:
            # Turnstile is disabled; permit scan with warning in dev/test
            logger.debug(
                "Burst threshold exceeded for %s but Turnstile is disabled",
                burst_key,
            )
            return

        site_key = settings.TURNSTILE_SITE_KEY or "1x0000000000000000000000000000000AA"
        if not turnstile_token or not turnstile_token.strip():
            logger.info(
                "Adaptive scan challenge triggered for %s (burst=%d)",
                burst_key,
                burst_count,
            )
            raise ScanChallengeRequiredError(
                site_key=site_key,
                message=(
                    "Verdachte scanfrequentie gedetecteerd. "
                    "Los de veiligheidscontrole op."
                ),
            )

        # Verify provided token
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
                    "site_key": site_key,
                },
                headers={"X-Challenge-Required": "turnstile"},
            )

        # Challenge passed! Clear burst window to restore smooth scanning
        cls.storage.clear_key(burst_key)
        logger.info("Adaptive challenge successfully solved for %s", burst_key)

    @classmethod
    def record_scan_activity(
        cls,
        request: Request,
        user_id: str | None = None,
    ) -> None:
        """Record successful scan hit in sliding-window rate and burst trackers.

        Must only be called after upload validation and image storage succeed.
        """
        now = time.time()
        client_ip = TurnstileService.get_trusted_client_ip(request)
        rate_key = f"rate:{client_ip}"
        burst_key = f"burst:{cls.get_client_identifier(request, user_id)}"

        cls.storage.record_hit(rate_key, now)
        cls.storage.record_hit(burst_key, now)

    @classmethod
    def check_and_record_scan(
        cls,
        request: Request,
        user_id: str | None = None,
        turnstile_token: str | None = None,
    ) -> None:
        """Convenience method checking permission and recording scan hit."""
        cls.check_scan_permission(
            request=request,
            user_id=user_id,
            turnstile_token=turnstile_token,
        )
        cls.record_scan_activity(request=request, user_id=user_id)
