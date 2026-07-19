"""Deterministic construction helpers for project-window findings.

Evidence IDs are stable for identical project / window / evidence / ruleset
input, and error-signature normalization is a redaction step: long tokens and
digit runs are collapsed so secrets, IDs, and free-form content never survive
into a signature label.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from uuid import UUID

from app.project_analyst.models import (
    Category,
    Confidence,
    ProjectEntityType,
    ProjectFinding,
    ProjectWindow,
    Severity,
    SupportingTraceRef,
)
from app.project_analyst.thresholds import (
    MAX_EXAMPLE_TRACES_PER_FINDING,
    MAX_STATEMENT_LEN,
    MAX_SUPPORTING_SPAN_IDS,
    PROJECT_RULESET_VERSION,
    SIGNATURE_EXCEPTION_TYPE_MAX_LEN,
    SIGNATURE_MESSAGE_MAX_LEN,
    SIGNATURE_TOKEN_MAX_LEN,
)

_DIGIT_RUN_RE = re.compile(r"\d+")
_WHITESPACE_RE = re.compile(r"\s+")


def trace_ui_path(trace_id: str) -> str:
    return f"/app/traces/{trace_id}"


def normalize_status_message(message: Any) -> str | None:
    """Collapse a status message into a bounded, redacted signature fragment.

    - whitespace runs collapse to one space,
    - digit runs collapse to ``#`` (request IDs, counts, timestamps),
    - any remaining token longer than ``SIGNATURE_TOKEN_MAX_LEN`` collapses to
      ``<long>`` (keys, JWTs, hashes, UUIDs, blobs),
    - the result is truncated to ``SIGNATURE_MESSAGE_MAX_LEN``.
    """
    if not isinstance(message, str):
        return None
    text = _WHITESPACE_RE.sub(" ", message).strip()
    if not text:
        return None
    text = _DIGIT_RUN_RE.sub("#", text)
    tokens = [
        token if len(token) <= SIGNATURE_TOKEN_MAX_LEN else "<long>"
        for token in text.split(" ")
    ]
    text = " ".join(tokens)
    if len(text) > SIGNATURE_MESSAGE_MAX_LEN:
        text = text[: SIGNATURE_MESSAGE_MAX_LEN - 1] + "…"
    return text


def normalize_exception_type(value: Any) -> str | None:
    """Bound an ``exception.type`` attribute; non-strings are ignored."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) > SIGNATURE_EXCEPTION_TYPE_MAX_LEN:
        text = text[: SIGNATURE_EXCEPTION_TYPE_MAX_LEN - 1] + "…"
    return text


def signature_label(
    *, span_name: str, exception_type: str | None, normalized_message: str | None
) -> str:
    parts = [f"span '{span_name}'"]
    if exception_type:
        parts.append(exception_type)
    if normalized_message:
        parts.append(normalized_message)
    return " · ".join(parts)


def bound_statement(text: str) -> str:
    if len(text) <= MAX_STATEMENT_LEN:
        return text
    return text[: MAX_STATEMENT_LEN - 1] + "…"


def make_project_evidence_id(
    *,
    rule_id: str,
    project_id: UUID,
    current_window: ProjectWindow,
    baseline_window: ProjectWindow,
    entity_type: ProjectEntityType,
    entity_label: str,
    metric_name: str,
    observed_value: Any,
) -> str:
    payload = {
        "ruleset": PROJECT_RULESET_VERSION,
        "rule_id": rule_id,
        "project_id": str(project_id),
        "current_window": [
            current_window.start.isoformat(),
            current_window.end.isoformat(),
        ],
        "baseline_window": [
            baseline_window.start.isoformat(),
            baseline_window.end.isoformat(),
        ],
        "entity_type": entity_type.value,
        "entity_label": entity_label,
        "metric_name": metric_name,
        "observed_value": observed_value,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"pev_{digest[:24]}"


def build_project_finding(
    *,
    rule_id: str,
    project_id: UUID,
    current_window: ProjectWindow,
    baseline_window: ProjectWindow,
    severity: Severity,
    confidence: Confidence,
    category: Category,
    statement: str,
    metric_name: str,
    observed_value: Any,
    baseline_value: Any | None = None,
    entity_type: ProjectEntityType,
    entity_label: str,
    supporting_traces: list[SupportingTraceRef] | None = None,
    supporting_span_ids: list[str] | None = None,
    sample_size: dict[str, int] | None = None,
    supporting_values: dict[str, Any] | None = None,
) -> ProjectFinding:
    evidence_id = make_project_evidence_id(
        rule_id=rule_id,
        project_id=project_id,
        current_window=current_window,
        baseline_window=baseline_window,
        entity_type=entity_type,
        entity_label=entity_label,
        metric_name=metric_name,
        observed_value=observed_value,
    )
    return ProjectFinding(
        evidence_id=evidence_id,
        rule_id=rule_id,
        ruleset_version=PROJECT_RULESET_VERSION,
        project_id=project_id,
        severity=severity,
        confidence=confidence,
        category=category,
        statement=bound_statement(statement),
        metric_name=metric_name,
        observed_value=observed_value,
        baseline_value=baseline_value,
        current_window=current_window,
        baseline_window=baseline_window,
        entity_type=entity_type,
        entity_label=entity_label,
        supporting_traces=list(supporting_traces or [])[:MAX_EXAMPLE_TRACES_PER_FINDING],
        supporting_span_ids=list(supporting_span_ids or [])[:MAX_SUPPORTING_SPAN_IDS],
        sample_size=dict(sample_size or {}),
        supporting_values=dict(supporting_values or {}),
    )
