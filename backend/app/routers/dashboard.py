from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import DashboardSummaryRead
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryRead)
def get_summary(
    project_slug: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    return dashboard_service.get_dashboard_summary(db, project_slug=project_slug)
