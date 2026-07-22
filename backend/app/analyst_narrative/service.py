"""Orchestrate optional narrative generation over deterministic analysis results.

Receives only a completed ``TraceAnalysisRead``. Never touches the database,
authorization context, or raw OTel detail.
"""

from __future__ import annotations

from collections.abc import Callable

from app.analyst_narrative.models import (
    NarrativeConfigSnapshot,
    NarrativeStatus,
    ProviderNarrative,
)
from app.analyst_narrative.provider import (
    NarrativeConfigurationError,
    NarrativeInvalidOutputError,
    NarrativeProvider,
    NarrativeProviderError,
    NarrativeUnsafeOutputError,
)
from app.analyst_narrative.providers.openai_provider import OpenAINarrativeProvider
from app.analyst_narrative.serializer import serialize_evidence_bundle
from app.analyst_narrative.validation import validate_provider_narrative
from app.config import Settings, get_settings
from app.schemas_analysis import (
    NarrativeFindingExplanationRead,
    TraceAnalysisNarrativeRead,
    TraceAnalysisRead,
)

ProviderFactory = Callable[[NarrativeConfigSnapshot, Settings], NarrativeProvider | None]


def resolve_narrative_config(settings: Settings | None = None) -> NarrativeConfigSnapshot:
    settings = settings or get_settings()
    key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else ""
    return NarrativeConfigSnapshot(
        enabled=bool(settings.helios_analyst_narrative_enabled),
        allow_third_party=bool(settings.helios_analyst_allow_third_party),
        provider=(settings.helios_analyst_provider or "").strip().lower(),
        model=(settings.helios_analyst_model or "").strip(),
        timeout_seconds=float(settings.helios_analyst_timeout_seconds),
        max_output_tokens=int(settings.helios_analyst_max_output_tokens),
        max_evidence_bytes=int(settings.helios_analyst_max_evidence_bytes),
        max_findings=int(settings.helios_analyst_max_findings),
        api_key_configured=bool(key),
    )


def narrative_is_configured(config: NarrativeConfigSnapshot) -> bool:
    if not config.enabled or not config.allow_third_party:
        return False
    if config.provider != "openai":
        return False
    if not config.model or not config.api_key_configured:
        return False
    return True


def default_provider_factory(
    config: NarrativeConfigSnapshot, settings: Settings
) -> NarrativeProvider | None:
    if not narrative_is_configured(config):
        return None
    key = settings.openai_api_key.get_secret_value()
    return OpenAINarrativeProvider(
        api_key=key,
        model=config.model,
        timeout_seconds=config.timeout_seconds,
        max_output_tokens=config.max_output_tokens,
    )


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


async def attach_narrative(
    analysis: TraceAnalysisRead,
    *,
    include_narrative: bool,
    settings: Settings | None = None,
    provider: NarrativeProvider | None = None,
    provider_factory: ProviderFactory | None = None,
) -> TraceAnalysisRead:
    """Return a copy of ``analysis`` with narrative_status / narrative filled.

    Deterministic finding fields are never altered by provider outcome.
    """
    base = analysis.model_copy(deep=True)
    if not include_narrative:
        base.narrative_status = "not_requested"
        base.narrative = None
        return base

    settings = settings or get_settings()
    config = resolve_narrative_config(settings)
    if not narrative_is_configured(config):
        base.narrative_status = "disabled"
        base.narrative = None
        return base

    factory = provider_factory or default_provider_factory
    active = provider if provider is not None else factory(config, settings)
    if active is None:
        base.narrative_status = "disabled"
        base.narrative = None
        return base

    try:
        bundle = serialize_evidence_bundle(
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
