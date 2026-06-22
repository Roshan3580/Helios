from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import DatasetSummaryRead
from app.services import dataset_service

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("", response_model=list[DatasetSummaryRead])
def list_datasets(
    project_slug: str | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    return dataset_service.list_datasets(db, project_slug=project_slug)
