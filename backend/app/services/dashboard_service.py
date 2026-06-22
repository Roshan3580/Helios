from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import EvaluationRun, Project, Trace, TraceStatus
from app.services.trace_service import _trace_to_read


def get_dashboard_summary(db: Session, *, project_slug: str | None = None) -> dict:
    trace_stmt = select(Trace).join(Trace.project).options(selectinload(Trace.project))
    if project_slug:
        trace_stmt = trace_stmt.where(Trace.project.has(slug=project_slug))
    traces = db.scalars(trace_stmt.order_by(Trace.created_at.desc())).all()

    project_stmt = select(func.count()).select_from(Project)
    if project_slug:
        project_stmt = project_stmt.where(Project.slug == project_slug)
    active_projects = db.scalar(project_stmt) or 0

    eval_stmt = select(EvaluationRun)
    if project_slug:
        eval_stmt = eval_stmt.join(EvaluationRun.project).where(
            EvaluationRun.project.has(slug=project_slug)
        )
    eval_runs = db.scalars(eval_stmt).all()

    total_requests = len(traces)
    total_tokens = sum(trace.total_tokens for trace in traces)
    estimated_cost_usd = sum(trace.estimated_cost_usd for trace in traces)
    avg_latency_ms = (
        sum(trace.latency_ms for trace in traces) / total_requests if total_requests else 0.0
    )
    error_count = sum(1 for trace in traces if trace.status == TraceStatus.error)
    error_rate = error_count / total_requests if total_requests else 0.0

    eval_pass_rate: float | None = None
    if eval_runs:
        eval_pass_rate = sum(run.accuracy for run in eval_runs) / len(eval_runs)

    citation_coverage: float | None = None
    if eval_runs:
        citation_coverage = sum(run.citation_coverage for run in eval_runs) / len(eval_runs)

    model_counts = Counter(trace.model for trace in traces)
    model_breakdown = [
        {
            "model": model,
            "count": count,
            "share_pct": round(count / total_requests * 100, 1) if total_requests else 0.0,
        }
        for model, count in model_counts.most_common()
    ]

    status_counts = Counter(trace.status for trace in traces)
    status_breakdown = [
        {
            "status": status,
            "count": count,
            "share_pct": round(count / total_requests * 100, 1) if total_requests else 0.0,
        }
        for status, count in status_counts.items()
    ]

    recent_traces = [_trace_to_read(trace) for trace in traces[:6]]

    return {
        "total_requests": total_requests,
        "avg_latency_ms": round(avg_latency_ms, 1),
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(estimated_cost_usd, 4),
        "error_rate": round(error_rate, 4),
        "eval_pass_rate": round(eval_pass_rate, 4) if eval_pass_rate is not None else None,
        "citation_coverage": round(citation_coverage, 4) if citation_coverage is not None else None,
        "active_projects": active_projects,
        "recent_trace_count": total_requests,
        "model_breakdown": model_breakdown,
        "status_breakdown": status_breakdown,
        "recent_traces": recent_traces,
        "demo": True,
    }
