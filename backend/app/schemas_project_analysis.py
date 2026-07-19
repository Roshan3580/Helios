"""Browser-safe API schemas for deterministic project-window analysis.

Mirrors the design of ``app.schemas_analysis`` (single-trace): the request can
select only an optional rule subset, the window length in hours, and the
optional narrative flag. It cannot override project, ``as_of``, thresholds,
provider, or model. The response carries only engine-approved evidence — no
raw content, credentials, JWTs, or user/organization identity.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas_analysis import TraceAnalysisNarrativeRead


class ProjectAnalysisRequest(BaseModel):
    """Command payload for one project-window analysis run.

    ``rules`` semantics match the single-trace API:
    - omitted or ``null`` → run every default ``project-window-v1`` rule
    - non-empty list → run only those rules (duplicates deduplicated,
      first occurrence wins)
    - empty list → rejected with 422

    ``hours`` selects the current window ``[as_of - hours, as_of)``; the
    baseline window is always the immediately preceding equal-length window.
    A client-supplied ``as_of`` is deliberately not accepted.
    """

    model_config = ConfigDict(extra="forbid")

    hours: int = Field(default=24, ge=1, le=720)
    rules: list[str] | None = None
    include_narrative: bool = False

    @field_validator("rules")
    @classmethod
    def _non_empty_and_deduplicated(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if len(value) == 0:
            raise ValueError(
                "rules must be omitted/null to run all default rules, "
                "or a non-empty list of rule IDs"
            )
        return list(dict.fromkeys(value))


class ProjectWindowRead(BaseModel):
    """Half-open UTC window: start inclusive, end exclusive."""

    start: datetime
    end: datetime


class SupportingTraceRead(BaseModel):
    trace_id: str
    service_name: str
    root_span_name: str | None = None
    start_time: datetime
    duration_ms: float
    span_count: int
    error_count: int
    trace_ui_path: str


class ProjectFindingRead(BaseModel):
    evidence_id: str
    rule_id: str
    ruleset_version: str
    severity: str
    confidence: str
    category: str
    statement: str
    metric_name: str
    observed_value: Any
    baseline_value: Any | None = None
    current_window: ProjectWindowRead
    baseline_window: ProjectWindowRead
    entity_type: str
    entity_label: str
    supporting_traces: list[SupportingTraceRead]
    supporting_span_ids: list[str]
    sample_size: dict[str, int]
    supporting_values: dict[str, Any]


class ProjectCoverageRead(BaseModel):
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
    current_sample_sparse: bool
    baseline_sample_sparse: bool


class ProjectBoundsRead(BaseModel):
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


class ProjectAnalysisRead(BaseModel):
    analysis_version: str
    mode: Literal["deterministic"]
    project_id: UUID
    generated_at: datetime
    hours: int
    current_window: ProjectWindowRead
    baseline_window: ProjectWindowRead
    findings: list[ProjectFindingRead]
    coverage: ProjectCoverageRead
    limitations: list[str]
    available_rules: list[str]
    executed_rules: list[str]
    bounds: ProjectBoundsRead
    narrative_status: Literal["not_requested", "disabled", "complete", "failed"] = (
        "not_requested"
    )
    narrative: TraceAnalysisNarrativeRead | None = None
