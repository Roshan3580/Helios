"""Incremental, idempotent persistence for normalized OTLP spans.

Idempotency policy (documented in docs/ADR_001_OTLP_TRACE_FOUNDATION.md):
- Trace identity is (project_id, trace_id); span identity is
  (project_id, trace_id, span_id).
- Spans are bulk-upserted with ON CONFLICT DO UPDATE: re-sending an
  identical batch changes nothing observable; re-sending a span_id with
  changed content deterministically overwrites it (last write wins).
- Trace summary rows keep their first-seen service_name/environment and
  first_seen_at; last_seen_at advances on every batch.
- All trace aggregates (start/end, span/error counts, root span) are
  recomputed from the spans actually stored in PostgreSQL — client-supplied
  trace-level aggregates are never trusted (OTLP has none anyway).
"""

import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import Project
from app.models_otel import STATUS_CODE_ERROR, OtelSpan, OtelTrace
from app.otlp.parser import NormalizedSpan


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ingest_spans(
    db: Session,
    project: Project,
    spans: list[NormalizedSpan],
    *,
    environment_fallback: str | None = None,
) -> dict[str, int]:
    """Upsert spans grouped by trace, then recompute per-trace summaries.

    Runs inside the caller's transaction; the caller commits or rolls back.
    """
    if not spans:
        return {"traces": 0, "spans": 0}

    now = _utc_now()
    by_trace: dict[str, list[NormalizedSpan]] = defaultdict(list)
    for span in spans:
        by_trace[span.trace_id].append(span)

    # 1) Upsert one summary row per trace; aggregates fixed up in step 3.
    trace_rows = []
    for trace_id, trace_spans in by_trace.items():
        first = trace_spans[0]
        trace_rows.append(
            {
                "id": uuid.uuid4(),
                "project_id": project.id,
                "trace_id": trace_id,
                "service_name": first.service_name,
                "environment": first.environment or environment_fallback,
                "first_seen_at": now,
                "last_seen_at": now,
                "start_time": min(s.start_time for s in trace_spans),
                "end_time": max(s.end_time for s in trace_spans),
                "created_at": now,
                "updated_at": now,
            }
        )

    trace_upsert = (
        pg_insert(OtelTrace)
        .values(trace_rows)
        .on_conflict_do_update(
            constraint="uq_otel_traces_project_trace",
            # First-seen identity fields are kept; only recency advances here.
            set_={"last_seen_at": now, "updated_at": now},
        )
        .returning(OtelTrace.id, OtelTrace.trace_id)
    )
    trace_ids_by_hex = {row.trace_id: row.id for row in db.execute(trace_upsert)}

    # 2) Bulk span upsert (one statement for the whole batch).
    span_rows = [
        {
            "id": uuid.uuid4(),
            "project_id": project.id,
            "otel_trace_id": trace_ids_by_hex[span.trace_id],
            "trace_id": span.trace_id,
            "span_id": span.span_id,
            "parent_span_id": span.parent_span_id,
            "name": span.name,
            "kind": span.kind,
            "start_time": span.start_time,
            "end_time": span.end_time,
            "duration_ns": span.duration_ns,
            "status_code": span.status_code,
            "status_message": span.status_message,
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
            "created_at": now,
            "updated_at": now,
        }
        for span in spans
    ]

    span_insert = pg_insert(OtelSpan).values(span_rows)
    content_columns = (
        "parent_span_id",
        "name",
        "kind",
        "start_time",
        "end_time",
        "duration_ns",
        "status_code",
        "status_message",
        "trace_state",
        "trace_flags",
        "resource_attributes",
        "scope_name",
        "scope_version",
        "scope_attributes",
        "attributes",
        "events",
        "links",
        "dropped_attributes_count",
        "dropped_events_count",
        "dropped_links_count",
    )
    span_upsert = span_insert.on_conflict_do_update(
        constraint="uq_otel_spans_project_trace_span",
        # Last write wins for span content; identity/created_at are preserved.
        set_={
            **{column: getattr(span_insert.excluded, column) for column in content_columns},
            "updated_at": now,
        },
    )
    db.execute(span_upsert)

    # 3) Recompute summaries from what is actually stored (never from client).
    for trace_id, otel_trace_pk in trace_ids_by_hex.items():
        aggregates = db.execute(
            select(
                func.min(OtelSpan.start_time),
                func.max(OtelSpan.end_time),
                func.count(OtelSpan.id),
                func.count(OtelSpan.id).filter(OtelSpan.status_code == STATUS_CODE_ERROR),
            ).where(OtelSpan.otel_trace_id == otel_trace_pk)
        ).one()

        root = db.execute(
            select(OtelSpan.span_id, OtelSpan.name)
            .where(
                OtelSpan.otel_trace_id == otel_trace_pk,
                OtelSpan.parent_span_id.is_(None),
            )
            .order_by(OtelSpan.start_time.asc())
            .limit(1)
        ).one_or_none()

        trace = db.get(OtelTrace, otel_trace_pk)
        trace.start_time = aggregates[0]
        trace.end_time = aggregates[1]
        trace.span_count = aggregates[2]
        trace.error_count = aggregates[3]
        trace.root_span_id = root.span_id if root else None
        trace.root_span_name = root.name if root else None
        trace.last_seen_at = now
        trace.updated_at = now

    db.flush()
    return {"traces": len(by_trace), "spans": len(spans)}
