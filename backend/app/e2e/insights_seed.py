"""Canonical OTEL seed data for browser E2E project-insights coverage."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models_otel import OtelSpan, OtelTrace


def _make_trace(
    db: Session,
    *,
    project,
    start: datetime,
    service: str,
    duration_ms: float = 100.0,
    spans: list[dict[str, Any]] | None = None,
) -> None:
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    trace_id = uuid4().hex
    end = start + timedelta(milliseconds=duration_ms)
    root_span_id = uuid4().hex[:16]
    span_rows: list[OtelSpan] = [
        OtelSpan(
            project_id=project.id,
            trace_id=trace_id,
            span_id=root_span_id,
            parent_span_id=None,
            name="agent.run",
            kind=2,
            start_time=start,
            end_time=end,
            duration_ns=int(duration_ms * 1_000_000),
            status_code=0,
            status_message=None,
            attributes={},
            resource_attributes={"service.name": service},
            scope_attributes={},
            events=[],
            links=[],
        )
    ]
    for spec in spans or []:
        offset = timedelta(milliseconds=float(spec.get("offset_ms", 1.0)))
        span_duration = float(spec.get("duration_ms", 10.0))
        span_start = start + offset
        span_rows.append(
            OtelSpan(
                project_id=project.id,
                trace_id=trace_id,
                span_id=uuid4().hex[:16],
                parent_span_id=root_span_id,
                name=str(spec.get("name", "child.op")),
                kind=1,
                start_time=span_start,
                end_time=span_start + timedelta(milliseconds=span_duration),
                duration_ns=int(span_duration * 1_000_000),
                status_code=int(spec.get("status_code", 0)),
                status_message=spec.get("status_message"),
                attributes=dict(spec.get("attributes", {})),
                resource_attributes={"service.name": service},
                scope_attributes={},
                events=[],
                links=[],
            )
        )
    error_count = sum(1 for row in span_rows if row.status_code == 2)
    trace = OtelTrace(
        project_id=project.id,
        trace_id=trace_id,
        service_name=service,
        environment=None,
        first_seen_at=start,
        last_seen_at=end,
        start_time=start,
        end_time=end,
        root_span_id=root_span_id,
        root_span_name="agent.run",
        span_count=len(span_rows),
        error_count=error_count,
    )
    db.add(trace)
    db.flush()
    for row in span_rows:
        row.otel_trace_id = trace.id
        db.add(row)
    db.flush()


def seed_error_rate_regression(
    db: Session, *, project, hours: int = 24
) -> dict[str, int]:
    """Seed current vs baseline windows that trigger service_error_rate_regression."""
    now = datetime.now(timezone.utc)
    current_base = now - timedelta(hours=2)
    baseline_base = now - timedelta(hours=hours + 6)
    error_traces = 0
    for index in range(10):
        is_error = index < 5
        spans: list[dict[str, Any]] = []
        if is_error:
            error_traces += 1
            spans.append(
                {
                    "name": "payments.charge",
                    "status_code": 2,
                    "status_message": "charge failed",
                }
            )
        _make_trace(
            db,
            project=project,
            start=current_base + timedelta(minutes=index),
            service="svc-api",
            spans=spans,
        )
    for index in range(10):
        _make_trace(
            db,
            project=project,
            start=baseline_base + timedelta(minutes=index),
            service="svc-api",
        )
    return {
        "current_traces": 10,
        "baseline_traces": 10,
        "error_traces": error_traces,
    }
