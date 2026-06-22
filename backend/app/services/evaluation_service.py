from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EvaluationRun


def _eval_to_read(run: EvaluationRun) -> dict:
    return {
        "id": run.id,
        "dataset_name": run.dataset_name,
        "prompt_name": run.prompt_name,
        "model": run.model,
        "accuracy": run.accuracy,
        "citation_coverage": run.citation_coverage,
        "latency_ms": run.latency_ms,
        "cost_usd": run.cost_usd,
        "status": run.status,
        "created_at": run.created_at,
    }


def list_evaluations(
    db: Session,
    *,
    project_slug: str | None = None,
) -> list[dict]:
    stmt = select(EvaluationRun)
    if project_slug:
        stmt = stmt.join(EvaluationRun.project).where(
            EvaluationRun.project.has(slug=project_slug)
        )
    stmt = stmt.order_by(EvaluationRun.created_at.desc())
    runs = db.scalars(stmt).all()
    return [_eval_to_read(run) for run in runs]
