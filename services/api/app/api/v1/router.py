from fastapi import APIRouter

from app.api.v1.cards import router as cards_router
from app.api.v1.collection import router as collection_router
from app.api.v1.health import router as health_router
from app.api.v1.scans import router as scans_router
from app.api.v1.sets import router as sets_router
from app.api.v1.testing import router as testing_router
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(health_router, tags=["Health"])
api_router.include_router(sets_router)
api_router.include_router(cards_router)
api_router.include_router(scans_router)
api_router.include_router(collection_router)

# Mount testing routes only in non-production environments
if settings.ENVIRONMENT != "production":
    api_router.include_router(testing_router)
