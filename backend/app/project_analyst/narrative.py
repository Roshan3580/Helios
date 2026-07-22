"""Optional narrative attachment for project-window analysis.

Reuses the provider-neutral Checkpoint 10 narrative layer end to end:
configuration resolution, the single OpenAI provider adapter, and the safety
validation that binds prose to existing evidence IDs. Only the evidence bundle
differs (see ``serialize_project_evidence_bundle``). Deterministic findings
are never altered by any provider outcome, and provider failure degrades to
``narrative_status="failed"`` — never a 500.
"""

from __future__ import annotations

from app.analyst_narrative.provider import (
    NarrativeConfigurationError,
    NarrativeInvalidOutputError,
    NarrativeProvider,
    NarrativeProviderError,
    NarrativeUnsafeOutputError,
)
from app.analyst_narrative import service as narrative_service
from app.analyst_narrative.models import ProviderNarrative
from app.analyst_narrative.service import ProviderFactory
from app.analyst_narrative.validation import validate_provider_narrative
from app.config import Settings
from app.project_analyst.serializer import serialize_project_evidence_bundle
from app.schemas_analysis import (
    NarrativeFindingExplanationRead,
    TraceAnalysisNarrativeRead,
)
from app.schemas_project_analysis import ProjectAnalysisRead


def _to_api_narrative(validated: ProviderNarrative) -> TraceAnalysisNarrativeRead:
    return TraceAnalysisNarrativeRead(
        summary=validated.summary,
        finding_explanations=[
            NarrativeFindingExplanationRead(
                evidence_id=item.evidence_id,
                explanation=item.explanation,
                remediation=item.remediation,
            )
            for item in validated.finding_explanations
        ],
        caveats=list(validated.caveats),
    )


async def attach_project_narrative(
    analysis: ProjectAnalysisRead,
    *,
    include_narrative: bool,
    settings: Settings | None = None,
    provider: NarrativeProvider | None = None,
    provider_factory: ProviderFactory | None = None,
) -> ProjectAnalysisRead:
    """Return a copy of ``analysis`` with narrative_status / narrative filled."""
    base = analysis.model_copy(deep=True)
    if not include_narrative:
        base.narrative_status = "not_requested"
        base.narrative = None
        return base

    # Resolved through the module so test injection (monkeypatching
    # app.analyst_narrative.service) governs both analysis routes identically.
    settings = settings or narrative_service.get_settings()
    config = narrative_service.resolve_narrative_config(settings)
    if not narrative_service.narrative_is_configured(config):
        base.narrative_status = "disabled"
        base.narrative = None
        return base

    factory = provider_factory or narrative_service.default_provider_factory
    active = provider if provider is not None else factory(config, settings)
    if active is None:
        base.narrative_status = "disabled"
        base.narrative = None
        return base

    try:
        bundle = serialize_project_evidence_bundle(
            base,
            max_findings=config.max_findings,
            max_bytes=config.max_evidence_bytes,
        )
        raw = await active.generate(bundle=bundle)
        validated = validate_provider_narrative(
            raw,
            allowed_evidence_ids={f.evidence_id for f in base.findings},
        )
        if bundle.evidence_truncated:
            caveat = (
                "Provider evidence was bounded for size; some deterministic "
                "findings may lack an explanation."
            )
            if caveat not in validated.caveats:
                validated.caveats = list(validated.caveats) + [caveat]
        base.narrative_status = "complete"
        base.narrative = _to_api_narrative(validated)
        return base
    except (
        NarrativeConfigurationError,
        NarrativeInvalidOutputError,
        NarrativeUnsafeOutputError,
        NarrativeProviderError,
        ValueError,
    ):
        base.narrative_status = "failed"
        base.narrative = None
        return base
