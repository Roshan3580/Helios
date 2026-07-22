"""Pure runner for deterministic single-trace analysis.

No database access, no network I/O, and no logging of telemetry content.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import UUID

from app.analyst.hierarchy import build_hierarchy
from app.analyst.models import (
    Finding,
    TelemetryCoverage,
    TraceAnalysisResult,
    severity_rank,
)
from app.analyst.redaction import (
    has_model_data,
    has_token_data,
    is_model_like,
    is_tool_like,
)
from app.analyst.rules import DEFAULT_RULE_IDS, RULE_REGISTRY
from app.analyst.thresholds import RULESET_VERSION
from app.models_otel import STATUS_CODE_ERROR
from app.schemas_v2 import OtelTraceDetailRead

MANDATORY_LIMITATIONS: tuple[str, ...] = (
    "Cost analysis is unavailable: Helios does not store a verified cost standard.",
    "RAG quality analysis is unavailable from canonical OTel telemetry.",
    "Citation quality analysis is unavailable from canonical OTel telemetry.",
    "Evaluation results are unavailable from canonical OTel telemetry.",
    "Content-based prompt/response analysis was not performed.",
)


class AnalystValidationError(ValueError):
    """Raised when the caller requests an unknown rule ID."""


def _coerce_trace_detail(trace_detail: OtelTraceDetailRead | dict[str, Any]) -> dict[str, Any]:
    if isinstance(trace_detail, OtelTraceDetailRead):
        return trace_detail.model_dump(mode="python")
    if isinstance(trace_detail, dict):
        return dict(trace_detail)
    raise TypeError("trace_detail must be OtelTraceDetailRead or dict")


def _coverage(hierarchy, spans: list[dict[str, Any]]) -> TelemetryCoverage:
    error_spans = sum(
        1 for n in hierarchy.nodes.values() if n.status_code == STATUS_CODE_ERROR
    )
    model_data = 0
    token_data = 0
    tool_like = 0
    model_like = 0
    for node in hierarchy.nodes.values():
        if has_model_data(node.attributes):
            model_data += 1
        if has_token_data(node.attributes):
            token_data += 1
        if is_tool_like(node.attributes):
            tool_like += 1
        if is_model_like(node.attributes):
            model_like += 1
    return TelemetryCoverage(
        total_spans=len(spans),
        error_spans=error_spans,
        spans_with_model_data=model_data,
        spans_with_token_data=token_data,
        tool_like_spans=tool_like,
        model_like_spans=model_like,
        orphan_spans=len(hierarchy.orphans),
    )


def _sort_findings(findings: list[Finding], hierarchy) -> list[Finding]:
    def sort_key(finding: Finding) -> tuple:
        first_span = finding.span_ids[0] if finding.span_ids else ""
        node = hierarchy.nodes.get(first_span)
        start = node.start_time.isoformat() if node else ""
        return (
            severity_rank(finding.severity),
            finding.rule_id,
            start,
            finding.evidence_id,
        )

    return sorted(findings, key=sort_key)


def analyze_trace(
    *,
    project_id: UUID,
    trace_detail: OtelTraceDetailRead | dict[str, Any],
    rules: Sequence[str] | None = None,
    generated_at: datetime | None = None,
) -> TraceAnalysisResult:
    """Analyze one canonical OTel trace detail into deterministic findings.

    ``generated_at`` may be injected for tests; production callers omit it.
    """
    detail = _coerce_trace_detail(trace_detail)
    trace_id = detail.get("trace_id")
    if not isinstance(trace_id, str) or not trace_id:
        raise AnalystValidationError("trace_detail.trace_id is required")

    rule_ids = list(DEFAULT_RULE_IDS if rules is None else rules)
    unknown = [rid for rid in rule_ids if rid not in RULE_REGISTRY]
    if unknown:
        raise AnalystValidationError(
            f"unknown analyst rule id(s): {', '.join(sorted(set(unknown)))}"
        )

    spans_raw = detail.get("spans") or []
    if not isinstance(spans_raw, list):
        spans_raw = []
    # Normalize to plain dicts without mutating caller objects.
    spans: list[dict[str, Any]] = []
    for item in spans_raw:
        if hasattr(item, "model_dump"):
            spans.append(item.model_dump(mode="python"))
        elif isinstance(item, dict):
            spans.append(dict(item))

    hierarchy = build_hierarchy(spans)
    findings: list[Finding] = []
    for rule_id in rule_ids:
        findings.extend(RULE_REGISTRY[rule_id](project_id, trace_id, detail, hierarchy))

    # Integrity: drop any finding that cites unknown spans (defensive).
    known = set(hierarchy.nodes)
    findings = [
        f
        for f in findings
        if f.project_id == project_id
        and f.trace_id == trace_id
        and all(sid in known for sid in f.span_ids)
    ]
    findings = _sort_findings(findings, hierarchy)

    ts = generated_at or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    return TraceAnalysisResult(
        ruleset_version=RULESET_VERSION,
        project_id=project_id,
        trace_id=trace_id,
        generated_at=ts,
        findings=findings,
        limitations=list(MANDATORY_LIMITATIONS),
        coverage=_coverage(hierarchy, spans),
    )
