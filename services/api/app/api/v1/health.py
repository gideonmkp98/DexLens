from fastapi import APIRouter, Response, status

from app.core.database import check_db_connection
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description=(
        "Check the operational status of the API and its MariaDB database connection."
    ),
)
def get_health(response: Response) -> HealthResponse:
    db_connected = check_db_connection()
    if db_connected:
        return HealthResponse(status="ok", database="connected")

    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="degraded", database="disconnected")
