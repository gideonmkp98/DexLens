import hashlib
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

HIBP_API_URL = "https://api.pwnedpasswords.com/range/"


class PwnedPasswordsUnavailableError(Exception):
    """Raised when the HIBP service is unavailable and fail-closed is active."""


def check_password_pwned(password: str) -> tuple[bool, int]:
    """Check whether a password appears in Have I Been Pwned Pwned Passwords.

    Security & Privacy Controls:
    1. The password is never logged in plaintext.
    2. The full SHA-1 hash is computed locally and never transmitted.
    3. Only the 5-character prefix of the SHA-1 hash is sent to the HIBP API.
    4. Suffix matching is performed entirely in memory locally.
    5. The complete SHA-1 hash and suffix are never logged.
    6. Strict timeout is enforced via settings.HIBP_API_TIMEOUT_SECONDS.
    7. Fail-open (default) allows registration when HIBP is down;
       fail-closed blocks registration.

    Returns:
        tuple[bool, int]: (is_pwned, breach_count)
    """
    if not settings.HIBP_API_ENABLED:
        return False, 0

    if not password:
        return False, 0

    # Local SHA-1 calculation
    sha1 = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix = sha1[:5]
    suffix = sha1[5:]

    url = f"{HIBP_API_URL}{prefix}"
    headers = {
        "User-Agent": "DexLens-TCG-Scanner/1.0",
        "Add-Padding": "true",  # Mitigates response length analysis attacks
    }

    try:
        with httpx.Client(timeout=settings.HIBP_API_TIMEOUT_SECONDS) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()

            # Suffixes are compared locally
            for line in response.text.splitlines():
                if ":" in line:
                    ret_suffix, count_str = line.split(":", 1)
                    if ret_suffix.strip().upper() == suffix:
                        try:
                            count = int(count_str.strip())
                        except ValueError:
                            count = 1
                        logger.warning(
                            "Password rejected: matches breach in HIBP (count=%d)",
                            count,
                        )
                        return True, count

            return False, 0

    except (httpx.TimeoutException, httpx.HTTPError, Exception) as exc:
        if settings.HIBP_FAIL_CLOSED:
            logger.error(
                "HIBP range API request failed; fail-closed strategy is active: %s",
                type(exc).__name__,
            )
            raise PwnedPasswordsUnavailableError(
                "Controle van wachtwoordbeveiliging is tijdelijk niet "
                "beschikbaar. Probeer het later opnieuw."
            ) from exc

        logger.warning(
            "HIBP range API request failed; fail-open strategy active "
            "(permitting password): %s",
            type(exc).__name__,
        )
        return False, 0
