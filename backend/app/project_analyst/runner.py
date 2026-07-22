"""Orchestrating runner for deterministic project-window analysis.

Resolves the exact current/baseline windows from one ``as_of`` instant, runs
the bounded evidence queries, executes the requested pure rules, validates
every cited trace/span reference against the collected evidence, and returns a
typed result. No database writes, no network calls, nothing persisted.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Sequence
from uuid import UUID

from sqlalchemy.orm import Session

from app.analyst.runner import AnalystValidationError
from app.project_analyst.models import (
    ProjectAnalysisBounds,
    ProjectAnalysisResult,
    ProjectFinding,
    ProjectWindow,
    ProjectWindowEvidence,
    severity_rank,
)
from app.project_analyst.queries import collect_project_evidence
from app.project_analyst.rules import (
    PROJECT_DEFAULT_RULE_IDS,
    PROJECT_RULE_REGISTRY,
    ProjectRuleContext,
)
from app.project_analyst.thresholds import (
    MAX_ERROR_GROUPS,
    MAX_ERROR_SPAN_CANDIDATES,
    MAX_EXAMPLE_TRACES_PER_FINDING,
    MAX_MODELS_ANALYZED,
    MAX_PROJECT_FINDINGS,
    MAX_SERVICES_ANALYZED,
    MAX_WINDOW_HOURS,
    MIN_WINDOW_HOURS,
    PROJECT_RULESET_VERSION,
)

# Stated on every response, including zero-finding responses.
PROJECT_MANDATORY_LIMITATIONS: tuple[str, ...] = (
    "Model and infrastructure cost are not determined: Helios does not store a "
    "verified cost standard.",
    "RAG answer quality and retrieval relevance are not determined from "
    "canonical OTel telemetry.",
    "Citation correctness is not determined from canonical OTel telemetry.",
    "Hallucination detection is not performed.",
    "Evaluation performance is not determined from canonical OTel telemetry.",
    "Prompt and response content quality are not assessed; captured content is "
    "excluded from analysis.",
    "Findings are window comparisons, not causal certainty, and suggested "
    "remediation is investigative rather than guaranteed.",
    "Findings depend on the telemetry attributes that instrumented services "
    "actually exported.",
    "Sparse baseline data reduces confidence in regression comparisons.",
    "Comparisons between time windows can be affected by changes in workload mix.",
)


def resolve_windows(*, hours: int, as_of: datetime) -> tuple[ProjectWindow, ProjectWindow]:
    """Current ``[as_of - hours, as_of)`` and baseline ``[as_of - 2h, as_of - h)``."""
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    else:
        as_of = as_of.astimezone(timezone.utc)
    span = timedelta(hours=hours)
    current = ProjectWindow(start=as_of - span, end=as_of)
    baseline = ProjectWindow(start=as_of - 2 * span, end=as_of - span)
    return current, baseline


def resolve_rule_ids(rules: Sequence[str] | None) -> list[str]:
    """Default set for ``None``; dedupe first-seen; typed error for unknown IDs."""
    if rules is None:
        return list(PROJECT_DEFAULT_RULE_IDS)
    rule_ids = list(dict.fromkeys(rules))
    if not rule_ids:
        raise AnalystValidationError(
            "rules must be omitted/null to run all default rules, "
            "or a non-empty list of rule IDs"
        )
    unknown = [rid for rid in rule_ids if rid not in PROJECT_RULE_REGISTRY]
    if unknown:
        raise AnalystValidationError(
            f"unknown project analyst rule id(s): {', '.join(sorted(set(unknown)))}"
        )
    return rule_ids


def _known_trace_ids(evidence: ProjectWindowEvidence) -> set[str]:
    known: set[str] = set()
    for examples in evidence.error_examples_by_service.values():
        known.update(ref.trace_id for ref in examples)
    for examples in evidence.slow_examples_by_service.values():
        known.update(ref.trace_id for ref in examples)
    for examples in evidence.slow_examples_by_model.values():
        known.update(ref.trace_id for ref in examples)
    for examples in evidence.token_examples_by_model.values():
        known.update(ref.trace_id for ref in examples)
    known.update(ref.trace_id for ref in evidence.outlier_examples)
    for cluster in evidence.error_clusters:
        known.update(ref.trace_id for ref in cluster.supporting_traces)
    known.update(ref.trace_id for ref in evidence.genai.supporting_traces)
    return known


def _sort_findings(findings: list[ProjectFinding]) -> list[ProjectFinding]:
    return sorted(
        findings,
        key=lambda f: (
            severity_rank(f.severity),
            f.rule_id,
            f.entity_label,
            f.evidence_id,
        ),
    )


def analyze_project_window(
    db: Session,
    *,
    project_id: UUID,
    hours: int,
    as_of: datetime | None = None,
    rules: Sequence[str] | None = None,
) -> ProjectAnalysisResult:
    """Run deterministic project-window analysis for one authorized project.

    ``as_of`` may be injected for tests; production callers omit it and the
    instant is selected once, at request start, in UTC. Raises
    ``AnalystValidationError`` for invalid hours or unknown/empty rule lists.
    """
    if hours < MIN_WINDOW_HOURS or hours > MAX_WINDOW_HOURS:
        raise AnalystValidationError(
            f"hours must be between {MIN_WINDOW_HOURS} and {MAX_WINDOW_HOURS}"
        )
    rule_ids = resolve_rule_ids(rules)
    generated_at = as_of or datetime.now(timezone.utc)
    current_window, baseline_window = resolve_windows(hours=hours, as_of=generated_at)
    generated_at = current_window.end

    evidence = collect_project_evidence(
        db,
        project_id=project_id,
        current_window=current_window,
        baseline_window=baseline_window,
    )
    ctx = ProjectRuleContext(
        project_id=project_id,
        current_window=current_window,
        baseline_window=baseline_window,
        evidence=evidence,
    )

    findings: list[ProjectFinding] = []
    for rule_id in rule_ids:
        findings.extend(PROJECT_RULE_REGISTRY[rule_id](ctx))

    # Defensive reference integrity: every cited trace must have been produced
    # by the project-bound evidence queries for this exact request.
    known = _known_trace_ids(evidence)
    for finding in findings:
        assert finding.project_id == project_id
        finding.supporting_traces = [
            ref
            for ref in finding.supporting_traces
            if ref.trace_id in known and ref.trace_ui_path == f"/app/traces/{ref.trace_id}"
        ]

    findings = _sort_findings(findings)
    findings_truncated = len(findings) > MAX_PROJECT_FINDINGS
    findings = findings[:MAX_PROJECT_FINDINGS]

    bounds = ProjectAnalysisBounds(
        max_findings=MAX_PROJECT_FINDINGS,
        max_example_traces_per_finding=MAX_EXAMPLE_TRACES_PER_FINDING,
        max_services_analyzed=MAX_SERVICES_ANALYZED,
        max_models_analyzed=MAX_MODELS_ANALYZED,
        max_error_groups=MAX_ERROR_GROUPS,
        max_error_span_candidates=MAX_ERROR_SPAN_CANDIDATES,
        services_truncated=evidence.services_truncated,
        models_truncated=evidence.models_truncated,
        error_groups_truncated=evidence.error_groups_truncated,
        error_span_candidates_truncated=evidence.error_span_candidates_truncated,
        findings_truncated=findings_truncated,
    )

    return ProjectAnalysisResult(
        ruleset_version=PROJECT_RULESET_VERSION,
        project_id=project_id,
        hours=hours,
        generated_at=generated_at,
        current_window=current_window,
        baseline_window=baseline_window,
        findings=findings,
        coverage=evidence.coverage,
        limitations=list(PROJECT_MANDATORY_LIMITATIONS),
        bounds=bounds,
    )
