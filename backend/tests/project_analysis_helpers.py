"""ORM seeding helpers for project-window analysis tests.

Direct ``otel_traces`` / ``otel_spans`` inserts with precise timestamps so
window-boundary behavior can be tested deterministically. OTLP ingestion
correctness is covered separately (test_otlp_endpoint / test_trace_ingestion);
these helpers only need canonical rows.
"""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta, timezone
from typing import Any

from app.models_otel import OtelSpan, OtelTrace

AS_OF = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)

_trace_counter = itertools.count(1)
_span_counter = itertools.count(1)


def next_trace_id() -> str:
    return f"{next(_trace_counter):032x}"


def next_span_id() -> str:
    return f"{next(_span_counter):016x}"


def make_trace(
    db,
    *,
    project,
    start: datetime,
    trace_id: str | None = None,
    service: str = "svc-a",
    duration_ms: float = 100.0,
    error: bool = False,
    root_name: str = "agent.run",
    environment: str | None = None,
    spans: list[dict[str, Any]] | None = None,
    root_span: bool = True,
) -> OtelTrace:
    """Insert one canonical trace with optional extra spans.

    ``spans`` entries accept: name, status_code, status_message, duration_ms,
    offset_ms, attributes, scope_name, parent_span_id, span_id.
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    trace_id = trace_id or next_trace_id()
    end = start + timedelta(milliseconds=duration_ms)

    span_rows: list[OtelSpan] = []
    root_span_id: str | None = None
    if root_span:
        root_span_id = next_span_id()
        span_rows.append(
            OtelSpan(
                project_id=project.id,
                trace_id=trace_id,
                span_id=root_span_id,
                parent_span_id=None,
                name=root_name,
                kind=2,
                start_time=start,
                end_time=end,
                duration_ns=int(duration_ms * 1_000_000),
                status_code=2 if error else 0,
                status_message="request failed" if error else None,
                attributes={},
                resource_attributes={"service.name": service},
                scope_attributes={},
                events=[],
                links=[],
            )
        )
    for spec in spans or []:
        offset = timedelta(milliseconds=spec.get("offset_ms", 1.0))
        span_duration = float(spec.get("duration_ms", 10.0))
        span_start = start + offset
        span_rows.append(
            OtelSpan(
                project_id=project.id,
                trace_id=trace_id,
                span_id=spec.get("span_id") or next_span_id(),
                parent_span_id=spec.get("parent_span_id", root_span_id),
                name=spec.get("name", "child.op"),
                kind=int(spec.get("kind", 1)),
                start_time=span_start,
                end_time=span_start + timedelta(milliseconds=span_duration),
                duration_ns=int(span_duration * 1_000_000),
                status_code=int(spec.get("status_code", 0)),
                status_message=spec.get("status_message"),
                attributes=dict(spec.get("attributes", {})),
                resource_attributes={"service.name": service},
                scope_name=spec.get("scope_name"),
                scope_attributes={},
                events=[],
                links=[],
            )
        )

    error_count = sum(1 for s in span_rows if s.status_code == 2)
    trace = OtelTrace(
        project_id=project.id,
        trace_id=trace_id,
        service_name=service,
        environment=environment,
        first_seen_at=start,
        last_seen_at=end,
        start_time=start,
        end_time=end,
        root_span_id=root_span_id,
        root_span_name=root_name if root_span else None,
        span_count=len(span_rows),
        error_count=error_count,
    )
    db.add(trace)
    db.flush()
    for row in span_rows:
        row.otel_trace_id = trace.id
        db.add(row)
    db.flush()
    return trace


def make_service_traces(
    db,
    *,
    project,
    service: str,
    window_start: datetime,
    total: int,
    errors: int = 0,
    duration_ms: float = 100.0,
    error_duration_ms: float | None = None,
    spacing_seconds: float = 60.0,
) -> list[OtelTrace]:
    """Insert ``total`` single-span traces spaced inside a window."""
    traces = []
    for index in range(total):
        is_error = index < errors
        traces.append(
            make_trace(
                db,
                project=project,
                service=service,
                start=window_start + timedelta(seconds=spacing_seconds * (index + 1)),
                duration_ms=(
                    error_duration_ms
                    if (is_error and error_duration_ms is not None)
                    else duration_ms
                ),
                error=is_error,
            )
        )
    return traces


def llm_attributes(
    *,
    model: str | None = "gpt-test",
    response_model: str | None = None,
    input_tokens: Any = None,
    output_tokens: Any = None,
    operation: str | None = "chat",
    span_type: str | None = None,
) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    if span_type is not None:
        attrs["helios.span.type"] = span_type
    if model is not None:
        attrs["gen_ai.request.model"] = model
    if response_model is not None:
        attrs["gen_ai.response.model"] = response_model
    if operation is not None:
        attrs["gen_ai.operation.name"] = operation
    if input_tokens is not None:
        attrs["gen_ai.usage.input_tokens"] = input_tokens
    if output_tokens is not None:
        attrs["gen_ai.usage.output_tokens"] = output_tokens
    return attrs
