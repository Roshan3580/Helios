"""Deterministic serializer for narrative provider input.

Only approved, engine-redacted finding fields are included. Raw OTel detail,
identity, credentials, and captured content are never serialized.
"""

from __future__ import annotations

import json
from typing import Any

from app.schemas_analysis import AnalysisFindingRead, TraceAnalysisRead
from app.analyst_narrative.models import (
    NarrativeEvidenceBundle,
    NarrativeEvidenceCoverage,
    NarrativeEvidenceFinding,
)

# Hard bounds applied to individual serialized strings (in addition to engine bounds).
MAX_STATEMENT_CHARS = 512
MAX_ATTR_VALUE_CHARS = 64
MAX_SUPPORTING_ATTRS = 12


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


def _sanitize_observed(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _bound_str(value, max_len=MAX_STATEMENT_CHARS)
    if isinstance(value, list):
        return [_sanitize_observed(item) for item in value[:20]]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key in sorted(value.keys())[:MAX_SUPPORTING_ATTRS]:
            if not isinstance(key, str):
                continue
            out[key] = _sanitize_observed(value[key])
        return out
    return _bound_str(value, max_len=MAX_ATTR_VALUE_CHARS)


def _serialize_finding(finding: AnalysisFindingRead) -> NarrativeEvidenceFinding:
    supporting: dict[str, Any] = {}
    for key in sorted(finding.supporting_attributes.keys())[:MAX_SUPPORTING_ATTRS]:
        if not isinstance(key, str):
            continue
        bound = _bound_str(
            finding.supporting_attributes[key], max_len=MAX_ATTR_VALUE_CHARS
        )
        if bound is not None:
            supporting[key] = bound
    statement = _bound_str(finding.statement, max_len=MAX_STATEMENT_CHARS) or ""
    return NarrativeEvidenceFinding(
        evidence_id=finding.evidence_id,
        rule_id=finding.rule_id,
        category=finding.category,
        severity=finding.severity,
        confidence=finding.confidence,
        statement=statement,
        metric_name=finding.metric_name,
        observed_value=_sanitize_observed(finding.observed_value),
        baseline_value=_sanitize_observed(finding.baseline_value),
        supporting_attributes=supporting,
    )


def _bundle_bytes(bundle: NarrativeEvidenceBundle) -> int:
    return len(
        json.dumps(
            bundle.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )


def serialize_evidence_bundle(
    analysis: TraceAnalysisRead,
    *,
    max_findings: int,
    max_bytes: int,
) -> NarrativeEvidenceBundle:
    """Build a bounded provider payload from a completed deterministic analysis.

    Truncation is deterministic (stable finding order, then drop trailing
    findings until under the byte budget). Deterministic API findings are
    never modified — only the provider payload is bounded.
    """
    if max_findings < 1:
        raise ValueError("max_findings must be >= 1")
    if max_bytes < 256:
        raise ValueError("max_bytes must be >= 256")

    total = len(analysis.findings)
    selected = analysis.findings[:max_findings]
    truncated = total > len(selected)

    coverage = NarrativeEvidenceCoverage(**analysis.coverage.model_dump())

    while True:
        findings = [_serialize_finding(f) for f in selected]
        bundle = NarrativeEvidenceBundle(
            analysis_version=analysis.analysis_version,
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
