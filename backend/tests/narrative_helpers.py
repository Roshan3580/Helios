"""Shared fakes and settings helpers for narrative-layer tests."""

from __future__ import annotations

from pydantic import SecretStr

from app.analyst_narrative.models import ProviderNarrative, NarrativeFindingExplanation
from app.analyst_narrative.provider import NarrativeUnavailableError
from app.config import Settings, get_settings
from app.schemas_analysis import TraceAnalysisRead


class FakeNarrativeProvider:
    """Deterministic fake provider injectable into the service/API layers."""

    def __init__(
        self,
        *,
        narrative: ProviderNarrative | None = None,
        error: Exception | None = None,
        fail_times: int = 0,
        retryable_error: Exception | None = None,
    ) -> None:
        self.narrative = narrative
        self.error = error
        self.fail_times = fail_times
        self.retryable_error = retryable_error or NarrativeUnavailableError("transient")
        self.calls = 0
        self.bundles: list = []

    async def generate(self, *, bundle):
        self.calls += 1
        self.bundles.append(bundle)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise self.retryable_error
        if self.error is not None:
            raise self.error
        assert self.narrative is not None
        return self.narrative


def make_valid_narrative(analysis: TraceAnalysisRead) -> ProviderNarrative:
    explanations = [
        NarrativeFindingExplanation(
            evidence_id=f.evidence_id,
            explanation=f"This finding ({f.rule_id}) is supported by the stored evidence.",
            remediation="Consider reviewing the cited spans for related errors.",
        )
        for f in analysis.findings[:3]
    ]
    return ProviderNarrative(
        summary="Deterministic findings summarize the stored telemetry for this trace.",
        finding_explanations=explanations,
        caveats=list(analysis.limitations[:2]),
    )


def enable_narrative_settings(**overrides) -> Settings:
    """Return Settings with narrative fully enabled for OpenAI (fake key)."""
    values = {
        "helios_analyst_narrative_enabled": True,
        "helios_analyst_allow_third_party": True,
        "helios_analyst_provider": "openai",
        "helios_analyst_model": "gpt-4o-mini",
        "helios_analyst_timeout_seconds": 5.0,
        "helios_analyst_max_output_tokens": 500,
        "helios_analyst_max_evidence_bytes": 24000,
        "helios_analyst_max_findings": 25,
        "openai_api_key": SecretStr("sk-test-not-a-real-key-0123456789abcdef"),
    }
    values.update(overrides)
    settings = Settings(**values)
    get_settings.cache_clear()
    return settings


def clear_settings_cache() -> None:
    get_settings.cache_clear()
