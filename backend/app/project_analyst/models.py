"""Typed models for project-window analysis: evidence inputs and findings.

Severity / confidence / category enums are shared with the single-trace engine
so the two rulesets present one vocabulary; the finding shape is deliberately
separate because project findings cite windows and entities, not one trace.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.analyst.models import Category, Confidence, Severity, severity_rank

__all__ = [
    "Category",
    "Confidence",
    "Severity",
    "severity_rank",
]


class ProjectWindow(BaseModel):
    """Half-open UTC window: ``start`` inclusive, ``end`` exclusive."""

    start: datetime
    end: datetime


class ProjectEntityType(str, Enum):
    SERVICE = "service"
    MODEL = "model"
    ERROR_SIGNATURE = "error_signature"
    INSTRUMENTATION = "instrumentation"
    PROJECT = "project"


class SupportingTraceRef(BaseModel):
    """Browser-safe reference to one real trace in the analyzed project."""

    trace_id: str
    service_name: str
    root_span_name: str | None = None
    start_time: datetime
    duration_ms: float
    span_count: int
    error_count: int
    trace_ui_path: str


class ProjectFinding(BaseModel):
    evidence_id: str
    rule_id: str
    ruleset_version: str
    project_id: UUID
    severity: Severity
    confidence: Confidence
    category: Category
    statement: str
    metric_name: str
    observed_value: Any
    baseline_value: Any | None = None
    current_window: ProjectWindow
    baseline_window: ProjectWindow
    entity_type: ProjectEntityType
    entity_label: str
    supporting_traces: list[SupportingTraceRef] = Field(default_factory=list)
    supporting_span_ids: list[str] = Field(default_factory=list)
    sample_size: dict[str, int] = Field(default_factory=dict)
    supporting_values: dict[str, Any] = Field(default_factory=dict)


class ProjectCoverage(BaseModel):
    """Factual data-coverage counts for both windows. Not a quality score."""

    current_trace_count: int
    baseline_trace_count: int
    current_span_count: int
    baseline_span_count: int
    current_error_trace_count: int
    baseline_error_trace_count: int
    services_observed: int
    models_observed: int
    model_like_span_count: int
    spans_with_model_data: int
    spans_with_token_data: int
    tool_like_span_count: int
    traces_without_root_span: int
    orphan_span_count: int
    # Indicative flags: fewer traces than the regression-rule minimum sample.
    current_sample_sparse: bool
    baseline_sample_sparse: bool


class ProjectAnalysisBounds(BaseModel):
    """Configured caps plus whether any candidate set was actually truncated."""

    max_findings: int
    max_example_traces_per_finding: int
    max_services_analyzed: int
    max_models_analyzed: int
    max_error_groups: int
    max_error_span_candidates: int
    services_truncated: bool
    models_truncated: bool
    error_groups_truncated: bool
    error_span_candidates_truncated: bool
    findings_truncated: bool


class ProjectAnalysisResult(BaseModel):
    ruleset_version: str
    project_id: UUID
    hours: int
    generated_at: datetime
    current_window: ProjectWindow
    baseline_window: ProjectWindow
    findings: list[ProjectFinding]
    coverage: ProjectCoverage
    limitations: list[str]
    bounds: ProjectAnalysisBounds


# ---------------------------------------------------------------------------
# Evidence structures produced by bounded SQL queries (inputs to pure rules).
# ---------------------------------------------------------------------------


class WindowAggregate(BaseModel):
    """Project-wide trace aggregates for one window."""

    trace_count: int
    error_trace_count: int
    span_count: int
    p50_duration_ms: float | None = None
    p95_duration_ms: float | None = None


class ServiceWindowStats(BaseModel):
    service_name: str
    trace_count: int
    error_trace_count: int
    p50_duration_ms: float | None = None
    p95_duration_ms: float | None = None


class ModelWindowStats(BaseModel):
    model: str
    span_count: int
    p50_duration_ms: float | None = None
    p95_duration_ms: float | None = None
    token_span_count: int = 0
    input_tokens: float = 0.0
    output_tokens: float = 0.0
    total_tokens: float = 0.0


class ErrorClusterStats(BaseModel):
    """One deterministic ERROR-span signature cluster in the current window."""

    signature_label: str
    span_name: str
    exception_type: str | None = None
    normalized_message: str | None = None
    occurrence_count: int
    distinct_trace_count: int
    supporting_traces: list[SupportingTraceRef] = Field(default_factory=list)
    supporting_span_ids: list[str] = Field(default_factory=list)


class GenAiGapStats(BaseModel):
    """Current-window model-like span instrumentation coverage."""

    model_like_span_count: int
    missing_model_count: int
    missing_token_count: int
    explicitly_classified_count: int
    supporting_traces: list[SupportingTraceRef] = Field(default_factory=list)
    supporting_span_ids: list[str] = Field(default_factory=list)


class ProjectWindowEvidence(BaseModel):
    """Everything the deterministic project rules are allowed to see.

    Built exclusively by :mod:`app.project_analyst.queries`; contains no ORM
    objects, no raw attribute payloads, and no content-bearing strings beyond
    span/root names and redaction-normalized error signatures.
    """

    current: WindowAggregate
    baseline: WindowAggregate
    current_services: list[ServiceWindowStats] = Field(default_factory=list)
    baseline_services: dict[str, ServiceWindowStats] = Field(default_factory=dict)
    services_truncated: bool = False
    current_models: list[ModelWindowStats] = Field(default_factory=list)
    baseline_models: dict[str, ModelWindowStats] = Field(default_factory=dict)
    models_truncated: bool = False
    error_examples_by_service: dict[str, list[SupportingTraceRef]] = Field(
        default_factory=dict
    )
    slow_examples_by_service: dict[str, list[SupportingTraceRef]] = Field(
        default_factory=dict
    )
    slow_examples_by_model: dict[str, list[SupportingTraceRef]] = Field(
        default_factory=dict
    )
    token_examples_by_model: dict[str, list[SupportingTraceRef]] = Field(
        default_factory=dict
    )
    outlier_count: int = 0
    outlier_examples: list[SupportingTraceRef] = Field(default_factory=list)
    error_clusters: list[ErrorClusterStats] = Field(default_factory=list)
    error_groups_truncated: bool = False
    error_span_candidates_truncated: bool = False
    genai: GenAiGapStats = Field(
        default_factory=lambda: GenAiGapStats(
            model_like_span_count=0,
            missing_model_count=0,
            missing_token_count=0,
            explicitly_classified_count=0,
        )
    )
    coverage: ProjectCoverage
