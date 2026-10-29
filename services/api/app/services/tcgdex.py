"""TCGdex integration facade for backwards compatibility with existing callers.

Direct HTTP request logic has been replaced with the official TCGdex Python SDK
via TCGdexProvider in app.integrations.tcgdex.
"""

from app.integrations.tcgdex.exceptions import (
    TcgdexConnectionError,
    TcgdexError,
    TcgdexInvalidLanguageError,
    TcgdexNotFoundError,
    TcgdexRateLimitError,
)
from app.integrations.tcgdex.mapper import (
    derive_image_urls,
    is_digital_card,
    is_digital_set,
)
from app.integrations.tcgdex.provider import TCGdexProvider

# Backwards-compatible alias for existing code
TcgdexClient = TCGdexProvider

__all__ = [
    "TcgdexClient",
    "TCGdexProvider",
    "TcgdexError",
    "TcgdexNotFoundError",
    "TcgdexRateLimitError",
    "TcgdexConnectionError",
    "TcgdexInvalidLanguageError",
    "is_digital_set",
    "is_digital_card",
    "derive_image_urls",
]
