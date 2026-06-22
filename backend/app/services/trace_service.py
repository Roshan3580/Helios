from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Span, Trace
from app.schemas import SpanCreate, TraceCreate
from app.services.project_service import get_or_create_project
from app.utils.ids import generate_id


def _trace_to_read(trace: Trace) -> dict:
    return {
        "id": trace.id,
        "trace_id": trace.trace_id,
        "project_slug": trace.project.slug,
        "user_query": trace.user_query,
        "app_name": trace.app_name,
        "model": trace.model,
        "status": trace.status,
        "latency_ms": trace.latency_ms,
        "total_tokens": trace.total_tokens,
        "prompt_tokens": trace.prompt_tokens,
        "completion_tokens": trace.completion_tokens,
        "estimated_cost_usd": trace.estimated_cost_usd,
        "created_at": trace.created_at,
    }


def list_traces(
    db: Session,
    *,
    project_slug: str | None = None,
    status: str | None = None,
    model: str | None = None,
    limit: int = 50,
) -> list[dict]:
    stmt = select(Trace).join(Trace.project).options(selectinload(Trace.project))
    if project_slug:
        stmt = stmt.where(Trace.project.has(slug=project_slug))
    if status:
        stmt = stmt.where(Trace.status == status)
    if model:
        stmt = stmt.where(Trace.model == model)
    stmt = stmt.order_by(Trace.created_at.desc()).limit(limit)
    traces = db.scalars(stmt).all()
    return [_trace_to_read(trace) for trace in traces]


def get_trace_detail(db: Session, trace_id: str) -> dict | None:
    trace = db.scalar(
        select(Trace)
        .where(Trace.trace_id == trace_id)
        .options(selectinload(Trace.project), selectinload(Trace.spans))
    )
    if not trace:
        return None
    payload = _trace_to_read(trace)
    payload["spans"] = sorted(trace.spans, key=lambda span: span.started_at)
    return payload


def create_trace(db: Session, payload: TraceCreate) -> dict:
    project = get_or_create_project(
        db,
        slug=payload.project_slug,
        name=payload.project_name,
        environment=payload.environment,
    )

    trace = Trace(
        project_id=project.id,
        trace_id=payload.trace_id,
        user_query=payload.user_query,
        app_name=payload.app_name,
        model=payload.model,
        status=payload.status,
        latency_ms=payload.latency_ms,
        total_tokens=payload.total_tokens,
        prompt_tokens=payload.prompt_tokens,
        completion_tokens=payload.completion_tokens,
        estimated_cost_usd=payload.estimated_cost_usd,
    )
    db.add(trace)
    db.flush()

    for span_payload in payload.spans:
        create_span(db, trace, span_payload)

    db.refresh(trace)
    return get_trace_detail(db, trace.trace_id)  # type: ignore[return-value]


def create_span(db: Session, trace: Trace, payload: SpanCreate) -> Span:
    span = Span(
        trace_id=trace.id,
        span_id=payload.span_id or generate_id("spn"),
        parent_span_id=payload.parent_span_id,
        name=payload.name,
        span_type=payload.span_type,
        provider=payload.provider,
        model=payload.model,
        latency_ms=payload.latency_ms,
        token_count=payload.token_count,
        cost_usd=payload.cost_usd,
        status=payload.status,
        input_preview=payload.input_preview,
        output_preview=payload.output_preview,
        metadata_json=payload.metadata_json,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
    )
    db.add(span)
    db.flush()
    return span


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
