from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PromptVersion


def _prompt_to_read(prompt: PromptVersion) -> dict:
    return {
        "id": prompt.id,
        "name": prompt.name,
        "version": prompt.version,
        "model": prompt.model,
        "eval_score": prompt.eval_score,
        "latency_ms": prompt.latency_ms,
        "cost_usd": prompt.cost_usd,
        "created_at": prompt.created_at,
    }


def list_prompts(
    db: Session,
    *,
    project_slug: str | None = None,
) -> list[dict]:
    stmt = select(PromptVersion)
    if project_slug:
        stmt = stmt.join(PromptVersion.project).where(
            PromptVersion.project.has(slug=project_slug)
        )
    stmt = stmt.order_by(PromptVersion.name, PromptVersion.created_at.desc())
    prompts = db.scalars(stmt).all()
    return [_prompt_to_read(prompt) for prompt in prompts]
