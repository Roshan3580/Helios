from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import EvaluationRun

# Sample dataset catalog — demo metadata for datasets referenced in eval runs.
DEMO_DATASET_CATALOG: dict[str, dict[str, int]] = {
    "support_qa.v4": {"total_cases": 412},
    "research_summaries.v2": {"total_cases": 218},
    "policy_retrieval.v1": {"total_cases": 96},
}


def list_datasets(
    db: Session,
    *,
    project_slug: str | None = None,
) -> list[dict]:
    stmt = select(
        EvaluationRun.dataset_name,
        func.count(EvaluationRun.id).label("linked_evaluation_count"),
        func.avg(EvaluationRun.accuracy).label("passing_rate"),
        func.max(EvaluationRun.created_at).label("last_run_at"),
    )
    if project_slug:
        stmt = stmt.join(EvaluationRun.project).where(
            EvaluationRun.project.has(slug=project_slug)
        )
    stmt = stmt.group_by(EvaluationRun.dataset_name).order_by(EvaluationRun.dataset_name)
    rows = db.execute(stmt).all()

    datasets: list[dict] = []
    seen: set[str] = set()

    for row in rows:
        name = row.dataset_name
        seen.add(name)
        catalog = DEMO_DATASET_CATALOG.get(name, {})
        datasets.append(
            {
                "name": name,
                "total_cases": catalog.get("total_cases", 0),
                "passing_rate": round(float(row.passing_rate or 0), 4),
                "last_run_at": row.last_run_at,
                "linked_evaluation_count": int(row.linked_evaluation_count),
            }
        )

    for name, catalog in DEMO_DATASET_CATALOG.items():
        if name in seen:
            continue
        datasets.append(
            {
                "name": name,
                "total_cases": catalog["total_cases"],
                "passing_rate": 0.0,
                "last_run_at": None,
                "linked_evaluation_count": 0,
            }
        )

    datasets.sort(key=lambda item: item["name"])
    return datasets
