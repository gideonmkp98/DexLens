from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import make_url, text
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.config import settings
from app.core.database import Base, engine, get_db

router = APIRouter(prefix="/testing", tags=["Testing"])


@router.get("/db-info")
def get_db_info() -> dict[str, object]:
    """Return database name and test-readiness status."""
    url = make_url(settings.DATABASE_URL)
    db_name = url.database or ""
    is_test = db_name.endswith("_test")
    return {
        "database": db_name,
        "is_test_database": is_test,
        "environment": settings.ENVIRONMENT,
    }


@router.post("/reset", status_code=status.HTTP_200_OK)
def reset_test_database(db: Session = Depends(get_db)) -> dict[str, str]:
    """Hard-guarded endpoint for resetting the test database.

    Refuses destructive operation unless the connected database ends in '_test'.
    """
    url = make_url(settings.DATABASE_URL)
    db_name = url.database or ""
    if not db_name.endswith("_test"):
        msg = (
            f"SAFETY GUARD REJECTION: Destructive database reset is strictly forbidden "
            f"on non-test database '{db_name}'. Connected database must end in '_test'."
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg)

    try:
        # Guarantee all model tables exist in the isolated test database
        Base.metadata.create_all(bind=engine)
        db.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset test database: {exc}",
        ) from exc

    return {
        "status": "success",
        "message": f"Successfully reset test database '{db_name}'.",
        "database": db_name,
    }
