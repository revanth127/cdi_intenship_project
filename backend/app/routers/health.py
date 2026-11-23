import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.schemas.health import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse, summary="Health Check with DB connectivity")
def get_health(db: Session = Depends(get_db)) -> HealthResponse:
    """
    Verifies that the API service is running and tests active connectivity to PostgreSQL.
    """
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as exc:
        logger.error("Database connectivity check failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unhealthy",
                "database": "disconnected",
                "environment": settings.ENVIRONMENT,
            },
        )

    return HealthResponse(
        status="healthy",
        database=db_status,
        environment=settings.ENVIRONMENT,
    )
