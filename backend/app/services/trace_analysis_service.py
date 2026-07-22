"""Application service for authenticated deterministic trace analysis.

Sits between the human-authenticated router and the pure engine in
``app.analyst``. Responsibilities:

- fetch canonical trace detail through the existing project-scoped read
  service (never an unscoped query),
- invoke the pure ``analyze_trace`` runner,
- convert the engine result into the browser-safe API schema,
- optionally attach an evidence-constrained narrative via
  ``app.analyst_narrative`` (never altering deterministic findings).

This module performs no database writes and no logging of telemetry content.
Results are ephemeral. Authorization stays in the router; the engine stays
pure; the narrative provider receives only a sanitized evidence bundle.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.analyst import analyze_trace
from app.analyst.models import TraceAnalysisResult
from app.analyst.rules import DEFAULT_RULE_IDS
from app.analyst_narrative.provider import NarrativeProvider
from app.analyst_narrative.service import attach_narrative
from app.models import Project
from app.schemas_analysis import (
    AnalysisCoverageRead,
    AnalysisFindingRead,
    TraceAnalysisRead,
)
from app.services import otel_trace_service

ANALYSIS_MODE = "deterministic"


def _to_api_response(result: TraceAnalysisResult, executed_rules: list[str]) -> TraceAnalysisRead:
    findings = [
        AnalysisFindingRead(
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
            span_ids=list(f.span_ids),
            source_start_time=f.source_start_time,
            source_end_time=f.source_end_time,
            supporting_attributes=dict(f.supporting_attributes),
            trace_ui_path=f.trace_ui_path,
            span_ui_selectors=list(f.span_ui_selectors),
        )
        for f in result.findings
    ]
    return TraceAnalysisRead(
        analysis_version=result.ruleset_version,
        mode=ANALYSIS_MODE,
        project_id=result.project_id,
        trace_id=result.trace_id,
        generated_at=result.generated_at,
        findings=findings,
        coverage=AnalysisCoverageRead(**result.coverage.model_dump()),
        limitations=list(result.limitations),
        available_rules=list(DEFAULT_RULE_IDS),
        executed_rules=executed_rules,
        narrative_status="not_requested",
        narrative=None,
    )


async def analyze_project_trace(
    db: Session,
    *,
    project: Project,
    trace_id: str,
    rules: Sequence[str] | None = None,
    include_narrative: bool = False,
    narrative_provider: NarrativeProvider | None = None,
) -> TraceAnalysisRead | None:
    """Run deterministic analysis (and optional narrative) for one project trace.

    Returns ``None`` when the trace does not exist in this project (the router
    maps that to 404). Raises ``AnalystValidationError`` for unknown rule IDs.
    Provider failures yield ``narrative_status="failed"`` with unchanged
    deterministic findings — never a 500 solely for narrative errors.
    """
    detail = otel_trace_service.get_trace_detail(
        db, project_slug=project.slug, trace_id=trace_id
    )
    if not detail:
        return None

    result = analyze_trace(
        project_id=project.id,
        trace_detail=detail,
        rules=list(rules) if rules is not None else None,
    )
    executed = list(DEFAULT_RULE_IDS) if rules is None else list(rules)
    analysis = _to_api_response(result, executed_rules=executed)
    return await attach_narrative(
        analysis,
        include_narrative=include_narrative,
        provider=narrative_provider,
    )
