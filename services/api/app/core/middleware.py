import logging
from ipaddress import ip_address
from typing import Any

from starlette.datastructures import Headers
from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware:
    """Attach baseline browser security headers to every API response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> Any:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def security_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"no-referrer"),
                    ]
                )
                if settings.ENVIRONMENT.lower() in {"production", "prod"}:
                    headers.append(
                        (
                            b"strict-transport-security",
                            b"max-age=31536000; includeSubDomains",
                        )
                    )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, security_send)


class RequestSizeLimitError(MultiPartException):
    """Raised when streaming request body exceeds configured byte ceiling."""


class RequestSizeLimitMiddleware:
    """Enforces request body size limits at the ASGI boundary.

    Guards against unbounded memory consumption during multipart parsing
    before FastAPI endpoints run. Checks Content-Length upfront and tracks
    incoming chunked stream bytes without Content-Length.
    """

    def __init__(self, app: ASGIApp, upload_prefix: str = "/api/v1/scans") -> None:
        self.app = app
        self.upload_prefix = upload_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> Any:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "").upper()
        path = scope.get("path", "")

        # Only enforce on upload paths
        if method in ("POST", "PUT", "PATCH") and path.startswith(self.upload_prefix):
            max_bytes = (
                settings.UPLOAD_MAX_BYTES + settings.UPLOAD_REQUEST_OVERHEAD_BYTES
            )
            headers = Headers(scope=scope)
            cl_header = headers.get("content-length")

            if cl_header is not None:
                try:
                    if int(cl_header) > max_bytes:
                        logger.warning(
                            "Rejected Content-Length %s > limit %s",
                            cl_header,
                            max_bytes,
                        )
                        res = JSONResponse(
                            status_code=413,
                            content={
                                "detail": {
                                    "code": "PAYLOAD_TOO_LARGE",
                                    "message": (
                                        f"Request body exceeds limit of "
                                        f"{max_bytes} bytes."
                                    ),
                                }
                            },
                        )
                        await res(scope, receive, send)
                        return
                except ValueError:
                    pass

            # Guard chunked streams without Content-Length
            total_bytes = 0
            response_started = False
            exceeded = False

            async def bounded_receive() -> Message:
                nonlocal total_bytes, exceeded
                message = await receive()
                if message["type"] == "http.request":
                    body_chunk = message.get("body", b"")
                    total_bytes += len(body_chunk)
                    if total_bytes > max_bytes:
                        logger.warning(
                            "Rejected chunked request: %s > limit %s",
                            total_bytes,
                            max_bytes,
                        )
                        exceeded = True
                        raise RequestSizeLimitError("Request payload too large")
                return message

            async def tracking_send(message: Message) -> None:
                nonlocal response_started
                if exceeded:
                    if message["type"] == "http.response.start":
                        response_started = True
                        res_obj = JSONResponse(
                            status_code=413,
                            content={
                                "detail": {
                                    "code": "PAYLOAD_TOO_LARGE",
                                    "message": (
                                        f"Request body exceeds limit of "
                                        f"{max_bytes} bytes."
                                    ),
                                }
                            },
                        )
                        await res_obj(scope, receive, send)
                        return
                    elif message["type"] == "http.response.body":
                        return

                if message["type"] == "http.response.start":
                    response_started = True
                await send(message)

            try:
                await self.app(scope, bounded_receive, tracking_send)
                return
            except RequestSizeLimitError:
                if not response_started:
                    res = JSONResponse(
                        status_code=413,
                        content={
                            "detail": {
                                "code": "PAYLOAD_TOO_LARGE",
                                "message": (
                                    f"Request body exceeds limit of {max_bytes} bytes."
                                ),
                            }
                        },
                    )
                    await res(scope, receive, send)
                    return
                raise

        await self.app(scope, receive, send)


class RateLimitMiddleware:
    """Sliding-window limiter for general, auth, and analytics API traffic."""

    windows: dict[tuple[str, str], list[float]] = {}

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.window_seconds = 60.0

    @classmethod
    def reset(cls) -> None:
        cls.windows.clear()

    def get_client_ip(self, scope: Scope) -> str:
        headers = Headers(scope=scope)
        client = scope.get("client")
        peer_ip = client[0] if client and len(client) > 0 else "127.0.0.1"
        x_forwarded = headers.get("x-forwarded-for")
        if x_forwarded and peer_ip in settings.TRUSTED_PROXY_IPS:
            forwarded_ip = x_forwarded.split(",")[0].strip()
            try:
                return str(ip_address(forwarded_ip))
            except ValueError:
                return peer_ip
        if client and len(client) > 0:
            return client[0]
        return "127.0.0.1"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> Any:
        import time

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        bucket = None
        limit = None
        if (
            path.startswith("/api/v1/auth/login")
            or path.startswith("/api/v1/auth/register")
            or path.startswith("/api/v1/auth/claim-anonymous-session")
        ):
            bucket = "auth"
            limit = settings.AUTH_RATE_LIMIT_PER_MINUTE
        elif path.startswith("/api/v1/analytics/events"):
            bucket = "analytics"
            limit = settings.ANALYTICS_RATE_LIMIT_PER_MINUTE
        elif path.startswith("/api/v1/") and not path.startswith("/api/v1/health"):
            bucket = "general"
            limit = settings.GENERAL_API_RATE_LIMIT_PER_MINUTE

        if bucket is not None and limit is not None:
            ip = self.get_client_ip(scope)
            now = time.time()
            key = (ip, bucket)

            if key not in self.windows:
                self.windows[key] = []

            cutoff = now - self.window_seconds
            if len(self.windows) > 10_000:
                stale_keys = [
                    window_key
                    for window_key, timestamps in self.windows.items()
                    if not timestamps or timestamps[-1] <= cutoff
                ]
                for stale_key in stale_keys:
                    self.windows.pop(stale_key, None)
            self.windows[key] = [t for t in self.windows[key] if t > cutoff]

            if len(self.windows[key]) >= limit:
                logger.warning(
                    "Rate limit exceeded on %s (%d requests)",
                    bucket,
                    len(self.windows[key]),
                )
                res = JSONResponse(
                    status_code=429,
                    content={
                        "detail": {
                            "code": "RATE_LIMIT_EXCEEDED",
                            "message": (
                                f"Rate limit of {limit} requests per minute exceeded. "
                                "Please try again later."
                            ),
                        }
                    },
                    headers={"Retry-After": "60"},
                )
                await res(scope, receive, send)
                return

            self.windows[key].append(now)

        await self.app(scope, receive, send)
