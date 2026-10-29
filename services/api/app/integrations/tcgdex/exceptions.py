class TcgdexError(Exception):
    """Base exception for TCGdex provider and integration errors."""


class TcgdexNotFoundError(TcgdexError):
    """Raised when a set or card resource is not found on TCGdex."""


class TcgdexRateLimitError(TcgdexError):
    """Raised when TCGdex rate limits are exceeded."""


class TcgdexConnectionError(TcgdexError):
    """Raised on connection failures, timeouts, or server errors."""


class TcgdexInvalidLanguageError(TcgdexError):
    """Raised when an unsupported language is requested."""
