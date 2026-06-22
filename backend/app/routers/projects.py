from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import ProjectRead
from app.services.project_service import list_projects

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectRead])
def get_projects(db: Session = Depends(get_db)) -> list[ProjectRead]:
    return list_projects(db)
