"""Typed models for the optional, evidence-constrained narrative layer."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

NarrativeStatus = Literal["not_requested", "disabled", "complete", "failed"]


class NarrativeFindingExplanation(BaseModel):
    """One prose explanation bound to a deterministic evidence ID."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    explanation: str
    remediation: str = ""


class ProviderNarrative(BaseModel):
    """Structured provider output before Helios safety validation."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    finding_explanations: list[NarrativeFindingExplanation] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


class NarrativeEvidenceFinding(BaseModel):
    """Sanitized finding fields safe to send to a narrative provider.

    ``entity_type``/``entity_label`` are populated only by the project-window
    serializer; single-trace bundles leave them unset (backward compatible).
    """

    evidence_id: str
    rule_id: str
    category: str
    severity: str
    confidence: str
    statement: str
    metric_name: str
    observed_value: Any = None
    baseline_value: Any | None = None
    entity_type: str | None = None
    entity_label: str | None = None
    supporting_attributes: dict[str, Any] = Field(default_factory=dict)


class NarrativeEvidenceCoverage(BaseModel):
    total_spans: int
    error_spans: int
    spans_with_model_data: int
    spans_with_token_data: int
    tool_like_spans: int
    model_like_spans: int
    orphan_spans: int


class NarrativeEvidenceBundle(BaseModel):
    """Bounded, redacted evidence payload for a narrative provider.

    Contains only deterministic analysis outputs — never raw OTel detail,
    identity, credentials, or captured prompt/response content.
    """

    analysis_version: str
    limitations: list[str]
    coverage: NarrativeEvidenceCoverage
    findings: list[NarrativeEvidenceFinding]
    evidence_truncated: bool = False
    findings_included: int = 0
    findings_total: int = 0


class ProjectNarrativeEvidenceBundle(BaseModel):
    """Bounded, redacted provider payload for project-window analysis.

    Contains only deterministic analysis outputs: version, window boundaries
    and durations, factual coverage counts, limitations, and sanitized
    findings. It never carries project names, organization or user identity,
    raw trace/span rows, trace IDs, credentials, or captured content —
    deterministic evidence links stay in the API response, outside the
    narrative path.
    """

    analysis_version: str
    window_hours: int
    current_window_start: str
    current_window_end: str
    baseline_window_start: str
    baseline_window_end: str
    limitations: list[str]
    coverage: dict[str, int]
    findings: list[NarrativeEvidenceFinding]
    evidence_truncated: bool = False
    findings_included: int = 0
    findings_total: int = 0


AnyNarrativeEvidenceBundle = NarrativeEvidenceBundle | ProjectNarrativeEvidenceBundle


class NarrativeConfigSnapshot(BaseModel):
    """Resolved narrative configuration with secrets omitted."""

    enabled: bool
    allow_third_party: bool
    provider: str
    model: str
    timeout_seconds: float
    max_output_tokens: int
    max_evidence_bytes: int
    max_findings: int
    api_key_configured: bool

    def __repr__(self) -> str:
        return (
            "NarrativeConfigSnapshot("
            f"enabled={self.enabled!r}, allow_third_party={self.allow_third_party!r}, "
            f"provider={self.provider!r}, model={self.model!r}, "
            f"api_key_configured={self.api_key_configured!r})"
        )
