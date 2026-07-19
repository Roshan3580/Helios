from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health/live")
def health_live() -> dict:
    """Process liveness — no database dependency."""
    return {"status": "ok", "service": "helios-api"}


@router.get("/health/ready")
def health_ready(response: Response, db: Session = Depends(get_db)) -> dict:
    """Readiness — bounded DB connectivity + migration table presence."""
    try:
        db.execute(text("SELECT 1"))
        # Confirm migrations have been applied at least once (table exists).
        row = db.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
        if row is None:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "not_ready", "reason": "migrations_pending"}
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "reason": "database_unavailable"}

    return {"status": "ready", "service": "helios-api"}


@router.get("/health")
def health_check(db: Session = Depends(get_db)) -> dict:
    """Legacy combined health probe (kept for older docs/clients)."""
    settings = get_settings()
    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "version": settings.app_version,
        "database": "connected" if db_ok else "unavailable",
        "demo_mode": settings.helios_demo_mode,
    }
