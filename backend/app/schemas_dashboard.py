"""Response models for authenticated project dashboard analytics.

Values are derived only from canonical otel_traces / otel_spans. There is no
cost field — Helios does not store a verified cost standard yet.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DashboardOverview(BaseModel):
    trace_count: int
    error_trace_count: int
    trace_error_rate: float
    total_span_count: int
    avg_duration_ms: float | None
    p50_duration_ms: float | None
    p95_duration_ms: float | None
    distinct_service_count: int


class DashboardTokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    spans_with_token_data: int


class DashboardServiceRow(BaseModel):
    service_name: str
    trace_count: int
    error_trace_count: int
    error_rate: float
    avg_duration_ms: float | None
    p50_duration_ms: float | None
    p95_duration_ms: float | None
    total_spans: int


class DashboardModelRow(BaseModel):
    model: str
    span_count: int
    trace_count: int
    input_tokens: int
    output_tokens: int
    error_span_count: int
    avg_duration_ms: float | None


class DashboardRecentError(BaseModel):
    trace_id: str
    service_name: str
    root_span_name: str | None
    start_time: datetime
    duration_ms: float
    span_count: int
    error_count: int


class DashboardLatencyBucket(BaseModel):
    bucket_start: datetime
    trace_count: int
    error_count: int
    avg_duration_ms: float | None
    p95_duration_ms: float | None


class ProjectDashboardRead(BaseModel):
    project_id: UUID
    project_slug: str
    hours: int = Field(ge=1, le=720)
    window_start: datetime
    window_end: datetime
    overview: DashboardOverview
    tokens: DashboardTokenUsage
    services: list[DashboardServiceRow]
    models: list[DashboardModelRow]
    recent_errors: list[DashboardRecentError]
    latency_trend: list[DashboardLatencyBucket]
