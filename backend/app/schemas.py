from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import RagChunkStatus, SpanStatus, SpanType, TraceStatus


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    environment: str
    created_at: datetime


class SpanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    span_id: str
    parent_span_id: str | None
    name: str
    span_type: SpanType
    provider: str | None
    model: str | None
    latency_ms: int
    token_count: int | None
    cost_usd: float | None
    status: SpanStatus
    input_preview: str | None
    output_preview: str | None
    metadata_json: dict[str, Any]
    started_at: datetime
    ended_at: datetime


class TraceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trace_id: str
    project_slug: str
    user_query: str
    app_name: str
    model: str
    status: TraceStatus
    latency_ms: int
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    created_at: datetime


class TraceDetailRead(TraceRead):
    spans: list[SpanRead]


class SpanCreate(BaseModel):
    span_id: str | None = None
    parent_span_id: str | None = None
    name: str
    span_type: SpanType
    provider: str | None = None
    model: str | None = None
    latency_ms: int = Field(ge=0)
    token_count: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    status: SpanStatus = SpanStatus.success
    input_preview: str | None = None
    output_preview: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime
    ended_at: datetime


class TraceCreate(BaseModel):
    trace_id: str
    project_slug: str
    project_name: str | None = None
    environment: str = "production"
    user_query: str
    app_name: str
    model: str
    status: TraceStatus = TraceStatus.success
    latency_ms: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    spans: list[SpanCreate] = Field(default_factory=list)

    @field_validator("latency_ms", "total_tokens", "prompt_tokens", "completion_tokens", "estimated_cost_usd")
    @classmethod
    def non_negative(cls, value: int | float) -> int | float:
        if value < 0:
            raise ValueError("must be non-negative")
        return value


class PromptVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    version: str
    model: str
    eval_score: float | None
    latency_ms: int | None
    cost_usd: float | None
    created_at: datetime


class EvaluationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dataset_name: str
    prompt_name: str
    model: str
    accuracy: float
    citation_coverage: float
    latency_ms: int
    cost_usd: float
    status: str
    created_at: datetime


class RagChunkMetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chunk_ref: str
    retrieval_hits: int
    quality_score: float
    status: RagChunkStatus
    created_at: datetime


class SeedResponse(BaseModel):
    project_slug: str
    traces_seeded: int
    prompt_versions_seeded: int
    evaluation_runs_seeded: int
    rag_chunk_metrics_seeded: int
    demo: bool = True


class ModelBreakdownItem(BaseModel):
    model: str
    count: int
    share_pct: float


class StatusBreakdownItem(BaseModel):
    status: TraceStatus
    count: int
    share_pct: float


class DashboardSummaryRead(BaseModel):
    total_requests: int
    avg_latency_ms: float
    total_tokens: int
    estimated_cost_usd: float
    error_rate: float
    eval_pass_rate: float | None
    citation_coverage: float | None
    active_projects: int
    recent_trace_count: int
    model_breakdown: list[ModelBreakdownItem]
    status_breakdown: list[StatusBreakdownItem]
    recent_traces: list[TraceRead]
    demo: bool = True


class RagMetricsRead(BaseModel):
    retrieval_hit_rate: float
    citation_coverage: float
    missing_source_rate: float
    avg_chunk_quality: float
    low_confidence_queries: list[str]
    top_failing_queries: list[str]
    chunk_metrics: list[RagChunkMetricRead]
    demo: bool = True


class DatasetSummaryRead(BaseModel):
    name: str
    total_cases: int
    passing_rate: float
    last_run_at: datetime | None
    linked_evaluation_count: int
