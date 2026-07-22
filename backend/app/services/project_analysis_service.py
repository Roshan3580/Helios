"""Application service for authenticated project-window analysis.

Sits between the human-authenticated router and the engine in
``app.project_analyst``. Fetches nothing outside the project the router
already authorized, performs no writes, logs no telemetry content, and keeps
results ephemeral. Narrative attachment reuses the Checkpoint 10 provider
layer and never alters deterministic findings.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.analyst_narrative.provider import NarrativeProvider
from app.models import Project
from app.project_analyst.narrative import attach_project_narrative
from app.project_analyst.runner import analyze_project_window, resolve_rule_ids
from app.project_analyst.serializer import to_api_response
from app.schemas_project_analysis import ProjectAnalysisRead


async def analyze_project(
    db: Session,
    *,
    project: Project,
    hours: int,
    rules: Sequence[str] | None = None,
    include_narrative: bool = False,
    narrative_provider: NarrativeProvider | None = None,
) -> ProjectAnalysisRead:
    """Run deterministic project-window analysis (and optional narrative).

    Raises ``AnalystValidationError`` for unknown/empty rule lists or invalid
    hours (the router maps that to 422). Provider failures yield
    ``narrative_status="failed"`` with unchanged deterministic findings.
    """
    executed_rules = resolve_rule_ids(list(rules) if rules is not None else None)
    result = analyze_project_window(
        db,
        project_id=project.id,
        hours=hours,
        rules=executed_rules,
    )
    analysis = to_api_response(result, executed_rules=executed_rules)
    return await attach_project_narrative(
        analysis,
        include_narrative=include_narrative,
        provider=narrative_provider,
    )
