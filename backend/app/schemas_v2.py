"""Response models for canonical v2 (OpenTelemetry) read APIs.

Intentionally separate from the legacy schemas: v2 responses carry only
what the OTel store actually holds. No user-query, model, token, or cost
fields exist at this level — GenAI signals live in span attributes exactly
as the client sent them.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class OtelTraceSummaryRead(BaseModel):
    trace_id: str
    project_slug: str
    service_name: str
    environment: str | None
    start_time: datetime
    end_time: datetime
    duration_ms: float
    root_span_id: str | None
    root_span_name: str | None
    span_count: int
    error_count: int
    first_seen_at: datetime
    last_seen_at: datetime


class OtelSpanRead(BaseModel):
    span_id: str
    parent_span_id: str | None
    name: str
    kind: int
    status_code: int
    status_message: str | None
    start_time: datetime
    end_time: datetime
    duration_ms: float
    trace_state: str | None
    trace_flags: int
    resource_attributes: dict[str, Any]
    scope_name: str | None
    scope_version: str | None
    scope_attributes: dict[str, Any]
    attributes: dict[str, Any]
    events: list[dict[str, Any]]
    links: list[dict[str, Any]]
    dropped_attributes_count: int
    dropped_events_count: int
    dropped_links_count: int


class OtelTraceDetailRead(OtelTraceSummaryRead):
    spans: list[OtelSpanRead]
