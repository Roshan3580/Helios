from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import RagMetricsRead
from app.services import rag_service

router = APIRouter(prefix="/rag", tags=["rag"])


@router.get("/metrics", response_model=RagMetricsRead)
def get_metrics(
    project_slug: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    return rag_service.get_rag_metrics(db, project_slug=project_slug)
