from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.middleware import (
    RateLimitMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.services.image_processor import ImageValidationError
from app.services.scan_quota import QuotaExhaustedError
from app.services.scan_session import ScanSessionError

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ImageValidationError)
async def handle_image_validation_error(
    request: Request, exc: ImageValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "detail": {"code": exc.code, "message": exc.message},
        },
    )


@app.exception_handler(ScanSessionError)
async def handle_scan_session_error(
    request: Request, exc: ScanSessionError
) -> JSONResponse:
    content = {
        "code": exc.code,
        "message": exc.message,
        "detail": {"code": exc.code, "message": exc.message},
    }
    headers: dict[str, str] = {}
    if exc.quota is not None:
        quota_dict = exc.quota.model_dump(mode="json")
        content["quota"] = quota_dict
        content["detail"]["quota"] = quota_dict
        reset_secs = max(0, int((exc.quota.reset_at - datetime.now(UTC)).total_seconds()))
        headers = {
            "Retry-After": str(reset_secs),
            "X-Quota-Limit": str(exc.quota.limit) if exc.quota.limit is not None else "unlimited",
            "X-Quota-Used": str(exc.quota.used),
            "X-Quota-Remaining": str(exc.quota.remaining) if exc.quota.remaining is not None else "unlimited",
            "X-Quota-Reset": exc.quota.reset_at.isoformat(),
            "X-Quota-Source": exc.quota.effective_source,
        }
    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=headers,
    )


@app.exception_handler(QuotaExhaustedError)
async def handle_quota_exhausted_error(
    request: Request, exc: QuotaExhaustedError
) -> JSONResponse:
    quota_dict = exc.quota.model_dump(mode="json")
    reset_secs = max(0, int((exc.quota.reset_at - datetime.now(UTC)).total_seconds()))
    headers = {
        "Retry-After": str(reset_secs),
        "X-Quota-Limit": str(exc.quota.limit) if exc.quota.limit is not None else "unlimited",
        "X-Quota-Used": str(exc.quota.used),
        "X-Quota-Remaining": str(exc.quota.remaining) if exc.quota.remaining is not None else "unlimited",
        "X-Quota-Reset": exc.quota.reset_at.isoformat(),
        "X-Quota-Source": exc.quota.effective_source,
    }
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "quota": quota_dict,
            "detail": {
                "code": exc.code,
                "message": exc.message,
                "quota": quota_dict,
            },
        },
        headers=headers,
    )


# Health & core v1 API router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/", include_in_schema=False)
def root():
    return {
        "service": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "docs": "/docs",
        "health": f"{settings.API_V1_PREFIX}/health",
    }
