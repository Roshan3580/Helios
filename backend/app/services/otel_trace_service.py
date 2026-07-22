"""Read queries for the canonical v2 OTel trace store.

Every query is project-scoped: project_slug is mandatory, so unscoped reads
are impossible in the v2 path (temporary pre-auth discipline; see ADR 001).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Project
from app.models_otel import OtelSpan, OtelTrace


def _ns_to_ms(duration_ns: int) -> float:
    return duration_ns / 1_000_000


def _trace_summary(trace: OtelTrace, project_slug: str) -> dict:
    duration_ns = max(
        0,
        int((trace.end_time - trace.start_time).total_seconds() * 1_000_000_000),
    )
    return {
        "trace_id": trace.trace_id,
        "project_slug": project_slug,
        "service_name": trace.service_name,
        "environment": trace.environment,
        "start_time": trace.start_time,
        "end_time": trace.end_time,
        "duration_ms": _ns_to_ms(duration_ns),
        "root_span_id": trace.root_span_id,
        "root_span_name": trace.root_span_name,
        "span_count": trace.span_count,
        "error_count": trace.error_count,
        "first_seen_at": trace.first_seen_at,
        "last_seen_at": trace.last_seen_at,
    }


def _span_read(span: OtelSpan) -> dict:
    return {
        "span_id": span.span_id,
        "parent_span_id": span.parent_span_id,
        "name": span.name,
        "kind": span.kind,
        "status_code": span.status_code,
        "status_message": span.status_message,
        "start_time": span.start_time,
        "end_time": span.end_time,
        "duration_ms": _ns_to_ms(span.duration_ns),
        "trace_state": span.trace_state,
        "trace_flags": span.trace_flags,
        "resource_attributes": span.resource_attributes,
        "scope_name": span.scope_name,
        "scope_version": span.scope_version,
        "scope_attributes": span.scope_attributes,
        "attributes": span.attributes,
        "events": span.events,
        "links": span.links,
        "dropped_attributes_count": span.dropped_attributes_count,
        "dropped_events_count": span.dropped_events_count,
        "dropped_links_count": span.dropped_links_count,
    }


def get_project_by_slug(db: Session, project_slug: str) -> Project | None:
    return db.scalar(select(Project).where(Project.slug == project_slug))


def list_traces(
    db: Session,
    *,
    project_slug: str,
    limit: int = 50,
    service_name: str | None = None,
    has_errors: bool | None = None,
) -> list[dict]:
    project = get_project_by_slug(db, project_slug)
    if not project:
        return []

    stmt = select(OtelTrace).where(OtelTrace.project_id == project.id)
    if service_name:
        stmt = stmt.where(OtelTrace.service_name == service_name)
    if has_errors is True:
        stmt = stmt.where(OtelTrace.error_count > 0)
    elif has_errors is False:
        stmt = stmt.where(OtelTrace.error_count == 0)
    stmt = stmt.order_by(OtelTrace.start_time.desc()).limit(limit)

    return [_trace_summary(trace, project_slug) for trace in db.scalars(stmt)]


def get_trace_detail(db: Session, *, project_slug: str, trace_id: str) -> dict | None:
    project = get_project_by_slug(db, project_slug)
    if not project:
        return None

    trace = db.scalar(
        select(OtelTrace)
        .where(OtelTrace.project_id == project.id, OtelTrace.trace_id == trace_id)
        .options(selectinload(OtelTrace.spans))
    )
    if not trace:
        return None

    detail = _trace_summary(trace, project_slug)
    # Relationship is ordered by start_time (see OtelTrace.spans order_by).
    detail["spans"] = [_span_read(span) for span in trace.spans]
    return detail
