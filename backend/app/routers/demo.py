from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.schemas import SeedResponse
from app.seed import seed_demo_data

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/seed", response_model=SeedResponse)
def seed_demo(db: Session = Depends(get_db)) -> SeedResponse:
    settings = get_settings()
    if not settings.helios_demo_mode:
        raise HTTPException(status_code=403, detail="Demo seeding is disabled")

    try:
        result = seed_demo_data(db)
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
