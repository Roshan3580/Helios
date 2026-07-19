"""Deterministic evidence/finding construction helpers."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from app.analyst.models import Category, Confidence, Finding, Severity
from app.analyst.thresholds import MAX_STATEMENT_LEN, RULESET_VERSION


def trace_ui_path(trace_id: str) -> str:
    return f"/app/traces/{trace_id}"


def span_ui_selector(span_id: str) -> str:
    return f"span:{span_id}"


def make_evidence_id(
    *,
    rule_id: str,
    project_id: UUID,
    trace_id: str,
    span_ids: list[str],
    metric_name: str,
    observed_value: Any,
) -> str:
    """Stable ID for identical trace data + ruleset version."""
    payload = {
        "ruleset": RULESET_VERSION,
        "rule_id": rule_id,
        "project_id": str(project_id),
        "trace_id": trace_id,
        "span_ids": list(span_ids),
        "metric_name": metric_name,
        "observed_value": observed_value,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"ev_{digest[:24]}"


def bound_statement(text: str) -> str:
    if len(text) <= MAX_STATEMENT_LEN:
        return text
    return text[: MAX_STATEMENT_LEN - 1] + "…"


def build_finding(
    *,
    rule_id: str,
    project_id: UUID,
    trace_id: str,
    span_ids: list[str],
    severity: Severity,
    confidence: Confidence,
    category: Category,
    statement: str,
    metric_name: str,
    observed_value: Any,
    baseline_value: Any | None = None,
    source_start_time: datetime | None = None,
    source_end_time: datetime | None = None,
    supporting_attributes: dict[str, Any] | None = None,
) -> Finding:
    ordered_spans = list(span_ids)
    evidence_id = make_evidence_id(
        rule_id=rule_id,
        project_id=project_id,
        trace_id=trace_id,
        span_ids=ordered_spans,
        metric_name=metric_name,
        observed_value=observed_value,
    )
    return Finding(
        evidence_id=evidence_id,
        rule_id=rule_id,
        ruleset_version=RULESET_VERSION,
        project_id=project_id,
        trace_id=trace_id,
        span_ids=ordered_spans,
        severity=severity,
        confidence=confidence,
        category=category,
        statement=bound_statement(statement),
        metric_name=metric_name,
        observed_value=observed_value,
        baseline_value=baseline_value,
        source_start_time=source_start_time,
        source_end_time=source_end_time,
        supporting_attributes=dict(supporting_attributes or {}),
        trace_ui_path=trace_ui_path(trace_id),
        span_ui_selectors=[span_ui_selector(sid) for sid in ordered_spans],
    )
