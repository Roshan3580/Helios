"""Serialization for project-window analysis.

Two responsibilities:
- convert the engine's ``ProjectAnalysisResult`` into the browser-safe API
  schema, and
- build the bounded, redacted provider payload for the optional narrative.

The narrative bundle deliberately excludes trace IDs, span IDs, supporting
trace references, project names, and any identity: evidence IDs are sufficient
for the provider to reference findings, and deterministic trace links remain
available in the API response outside the narrative path.
"""

from __future__ import annotations

import json
from typing import Any

from app.analyst_narrative.models import (
    NarrativeEvidenceFinding,
    ProjectNarrativeEvidenceBundle,
)
from app.project_analyst.models import ProjectAnalysisResult
from app.project_analyst.rules import PROJECT_DEFAULT_RULE_IDS
from app.schemas_project_analysis import (
    ProjectAnalysisRead,
    ProjectBoundsRead,
    ProjectCoverageRead,
    ProjectFindingRead,
    ProjectWindowRead,
    SupportingTraceRead,
)

ANALYSIS_MODE = "deterministic"

# Bounds applied to serialized narrative values (mirrors the single-trace
# serializer in app.analyst_narrative.serializer).
MAX_STATEMENT_CHARS = 512
MAX_VALUE_CHARS = 64
MAX_SUPPORTING_VALUES = 12


def to_api_response(
    result: ProjectAnalysisResult, *, executed_rules: list[str]
) -> ProjectAnalysisRead:
    findings = [
        ProjectFindingRead(
            evidence_id=f.evidence_id,
            rule_id=f.rule_id,
            ruleset_version=f.ruleset_version,
            severity=f.severity.value,
            confidence=f.confidence.value,
            category=f.category.value,
            statement=f.statement,
            metric_name=f.metric_name,
            observed_value=f.observed_value,
            baseline_value=f.baseline_value,
            current_window=ProjectWindowRead(
                start=f.current_window.start, end=f.current_window.end
            ),
            baseline_window=ProjectWindowRead(
                start=f.baseline_window.start, end=f.baseline_window.end
            ),
            entity_type=f.entity_type.value,
            entity_label=f.entity_label,
            supporting_traces=[
                SupportingTraceRead(**ref.model_dump()) for ref in f.supporting_traces
            ],
            supporting_span_ids=list(f.supporting_span_ids),
            sample_size=dict(f.sample_size),
            supporting_values=dict(f.supporting_values),
        )
        for f in result.findings
    ]
    return ProjectAnalysisRead(
        analysis_version=result.ruleset_version,
        mode=ANALYSIS_MODE,
        project_id=result.project_id,
        generated_at=result.generated_at,
        hours=result.hours,
        current_window=ProjectWindowRead(
            start=result.current_window.start, end=result.current_window.end
        ),
        baseline_window=ProjectWindowRead(
            start=result.baseline_window.start, end=result.baseline_window.end
        ),
        findings=findings,
        coverage=ProjectCoverageRead(**result.coverage.model_dump()),
        limitations=list(result.limitations),
        available_rules=list(PROJECT_DEFAULT_RULE_IDS),
        executed_rules=executed_rules,
        bounds=ProjectBoundsRead(**result.bounds.model_dump()),
        narrative_status="not_requested",
        narrative=None,
    )


def _bound_str(value: Any, *, max_len: int) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, (int, float)):
        text = str(value)
    elif isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
        except TypeError:
            return None
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def _sanitize_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _bound_str(value, max_len=MAX_VALUE_CHARS)
    return _bound_str(value, max_len=MAX_VALUE_CHARS)


def _serialize_finding(finding) -> NarrativeEvidenceFinding:
    supporting: dict[str, Any] = {}
    merged: dict[str, Any] = {**finding.sample_size, **finding.supporting_values}
    for key in sorted(merged.keys())[:MAX_SUPPORTING_VALUES]:
        if not isinstance(key, str):
            continue
        bounded = _sanitize_value(merged[key])
        if bounded is not None:
            supporting[key] = bounded
    return NarrativeEvidenceFinding(
        evidence_id=finding.evidence_id,
        rule_id=finding.rule_id,
        category=finding.category,
        severity=finding.severity,
        confidence=finding.confidence,
        statement=_bound_str(finding.statement, max_len=MAX_STATEMENT_CHARS) or "",
        metric_name=finding.metric_name,
        observed_value=_sanitize_value(finding.observed_value),
        baseline_value=_sanitize_value(finding.baseline_value),
        entity_type=finding.entity_type,
        entity_label=_bound_str(finding.entity_label, max_len=MAX_VALUE_CHARS),
        supporting_attributes=supporting,
    )


def _bundle_bytes(bundle: ProjectNarrativeEvidenceBundle) -> int:
    return len(
        json.dumps(
            bundle.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )


def serialize_project_evidence_bundle(
    analysis: ProjectAnalysisRead,
    *,
    max_findings: int,
    max_bytes: int,
) -> ProjectNarrativeEvidenceBundle:
    """Build a bounded provider payload from a completed project analysis.

    Truncation is deterministic: stable finding order, drop trailing findings
    until under the byte budget. The API response is never modified — only the
    provider payload is bounded.
    """
    if max_findings < 1:
        raise ValueError("max_findings must be >= 1")
    if max_bytes < 256:
        raise ValueError("max_bytes must be >= 256")

    coverage = {
        key: value
        for key, value in analysis.coverage.model_dump().items()
        if isinstance(value, int) and not isinstance(value, bool)
    }

    total = len(analysis.findings)
    selected = analysis.findings[:max_findings]
    truncated = total > len(selected)

    while True:
        findings = [_serialize_finding(f) for f in selected]
        bundle = ProjectNarrativeEvidenceBundle(
            analysis_version=analysis.analysis_version,
            window_hours=analysis.hours,
            current_window_start=analysis.current_window.start.isoformat(),
            current_window_end=analysis.current_window.end.isoformat(),
            baseline_window_start=analysis.baseline_window.start.isoformat(),
            baseline_window_end=analysis.baseline_window.end.isoformat(),
            limitations=list(analysis.limitations),
            coverage=coverage,
            findings=findings,
            evidence_truncated=truncated or len(selected) < total,
            findings_included=len(findings),
            findings_total=total,
        )
        if _bundle_bytes(bundle) <= max_bytes or not selected:
            return bundle
        selected = selected[:-1]
        truncated = True
