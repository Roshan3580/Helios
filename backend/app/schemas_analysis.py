"""Browser-safe API schemas for deterministic trace analysis.

Thin conversion layer over the pure engine models in ``app.analyst``:

- The request cannot override project, trace, ruleset version, severity, or
  thresholds; the only accepted field is an optional rule-ID subset.
- The response never carries raw JWTs, project API keys, prompt/completion
  content, or attributes beyond what the engine's redaction layer approved.
- ``mode`` is fixed to ``"deterministic"``: no external LLM is involved.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class TraceAnalysisRequest(BaseModel):
    """Command payload for one deterministic analysis run.

    ``rules`` semantics:
    - omitted or ``null`` → run every default ``single-trace-v1`` rule
    - non-empty list → run only those rules (duplicates are deduplicated,
      first occurrence wins)
    - empty list → rejected with 422 (a run that executes nothing is
      considered a caller error, not a valid analysis)

    Unknown fields are rejected (422) so the contract cannot silently grow
    ``include_content``-style options.
    """

    model_config = ConfigDict(extra="forbid")

    rules: list[str] | None = None

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
        # Deduplicate while preserving first-seen order.
        return list(dict.fromkeys(value))


class AnalysisFindingRead(BaseModel):
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
    span_ids: list[str]
    source_start_time: datetime | None = None
    source_end_time: datetime | None = None
    supporting_attributes: dict[str, Any]
    trace_ui_path: str
    span_ui_selectors: list[str]


class AnalysisCoverageRead(BaseModel):
    total_spans: int
    error_spans: int
    spans_with_model_data: int
    spans_with_token_data: int
    tool_like_spans: int
    model_like_spans: int
    orphan_spans: int


class TraceAnalysisRead(BaseModel):
    analysis_version: str
    mode: Literal["deterministic"]
    project_id: UUID
    trace_id: str
    generated_at: datetime
    findings: list[AnalysisFindingRead]
    coverage: AnalysisCoverageRead
    limitations: list[str]
    available_rules: list[str]
    executed_rules: list[str]
