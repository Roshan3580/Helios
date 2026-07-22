"""Typed models for deterministic single-trace analyst findings."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Category(str, Enum):
    PERFORMANCE = "performance"
    RELIABILITY = "reliability"
    EFFICIENCY = "efficiency"
    INSTRUMENTATION = "instrumentation"


_SEVERITY_RANK = {
    Severity.ERROR: 0,
    Severity.WARNING: 1,
    Severity.INFO: 2,
}


class Finding(BaseModel):
    evidence_id: str
    rule_id: str
    ruleset_version: str
    project_id: UUID
    trace_id: str
    span_ids: list[str] = Field(default_factory=list)
    severity: Severity
    confidence: Confidence
    category: Category
    statement: str
    metric_name: str
    observed_value: Any
    baseline_value: Any | None = None
    source_start_time: datetime | None = None
    source_end_time: datetime | None = None
    supporting_attributes: dict[str, Any] = Field(default_factory=dict)
    trace_ui_path: str
    span_ui_selectors: list[str] = Field(default_factory=list)


class TelemetryCoverage(BaseModel):
    total_spans: int
    error_spans: int
    spans_with_model_data: int
    spans_with_token_data: int
    tool_like_spans: int
    model_like_spans: int
    orphan_spans: int


class TraceAnalysisResult(BaseModel):
    ruleset_version: str
    project_id: UUID
    trace_id: str
    generated_at: datetime
    findings: list[Finding]
    limitations: list[str]
    coverage: TelemetryCoverage


def severity_rank(severity: Severity) -> int:
    return _SEVERITY_RANK[severity]
