from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import PromptVersionRead
from app.services import prompt_service

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.get("", response_model=list[PromptVersionRead])
def list_prompts(
    project_slug: str | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    return prompt_service.list_prompts(db, project_slug=project_slug)
