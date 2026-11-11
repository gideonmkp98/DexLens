from fastapi import APIRouter, Depends

from app.api.deps import require_admin_user
from app.api.v1.admin.abuse import router as abuse_router
from app.api.v1.admin.audit import router as audit_router
from app.api.v1.admin.beta import router as beta_router
from app.api.v1.admin.quotas import router as quotas_router
from app.api.v1.admin.users import router as users_router

admin_router = APIRouter(
    prefix="/admin",
    tags=["Administration"],
    dependencies=[Depends(require_admin_user)],
)

admin_router.include_router(users_router)
admin_router.include_router(quotas_router)
admin_router.include_router(beta_router)
admin_router.include_router(audit_router)
admin_router.include_router(abuse_router)
