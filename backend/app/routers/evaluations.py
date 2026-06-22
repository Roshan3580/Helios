from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import EvaluationRunRead
from app.services import evaluation_service

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.get("", response_model=list[EvaluationRunRead])
def list_evaluations(
    project_slug: str | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    return evaluation_service.list_evaluations(db, project_slug=project_slug)
