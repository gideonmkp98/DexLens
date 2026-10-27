import logging
from typing import Any

from starlette.datastructures import Headers
from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

logger = logging.getLogger(__name__)


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
