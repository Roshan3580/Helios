"""Service-level narrative status and fallback tests (no network)."""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.analyst_narrative.models import NarrativeFindingExplanation, ProviderNarrative
from app.analyst_narrative.provider import (
    NarrativeRateLimitError,
    NarrativeTimeoutError,
)
from app.analyst_narrative.providers.openai_provider import OpenAINarrativeProvider
from app.analyst_narrative.service import attach_narrative, resolve_narrative_config
from app.config import Settings
from app.schemas_analysis import (
    AnalysisCoverageRead,
    AnalysisFindingRead,
    TraceAnalysisRead,
)
from narrative_helpers import FakeNarrativeProvider, clear_settings_cache, make_valid_narrative


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def _analysis() -> TraceAnalysisRead:
    finding = AnalysisFindingRead(
        evidence_id="ev_service_test_00000001",
        rule_id="error_span",
        ruleset_version="single-trace-v1",
        severity="error",
        confidence="high",
        category="reliability",
        statement="Span recorded ERROR",
        metric_name="span.status_code",
        observed_value=2,
        baseline_value=None,
        span_ids=["abcd"],
        source_start_time=datetime.now(timezone.utc),
        source_end_time=datetime.now(timezone.utc),
        supporting_attributes={"name": "tool.fail"},
        trace_ui_path="/app/traces/t",
        span_ui_selectors=["span:abcd"],
    )
    return TraceAnalysisRead(
        analysis_version="single-trace-v1",
        mode="deterministic",
        project_id=uuid4(),
        trace_id="a" * 32,
        generated_at=datetime.now(timezone.utc),
        findings=[finding],
        coverage=AnalysisCoverageRead(
            total_spans=1,
            error_spans=1,
            spans_with_model_data=0,
            spans_with_token_data=0,
            tool_like_spans=1,
            model_like_spans=0,
            orphan_spans=0,
        ),
        limitations=[
            "Cost analysis is unavailable: Helios does not store a verified cost standard.",
            "RAG quality analysis is unavailable from canonical OTel telemetry.",
        ],
        available_rules=["error_span"],
        executed_rules=["error_span"],
    )


def _enabled_settings(**overrides) -> Settings:
    values = dict(
        helios_analyst_narrative_enabled=True,
        helios_analyst_allow_third_party=True,
        helios_analyst_provider="openai",
        helios_analyst_model="gpt-4o-mini",
        openai_api_key=SecretStr("sk-test-not-a-real-key-0123456789abcdef"),
    )
    values.update(overrides)
    return Settings(**values)


def _assert_deterministic_unchanged(before: TraceAnalysisRead, after: TraceAnalysisRead):
    assert [f.evidence_id for f in before.findings] == [
        f.evidence_id for f in after.findings
    ]
    assert before.coverage.model_dump() == after.coverage.model_dump()
    assert before.limitations == after.limitations
    assert before.findings[0].statement == after.findings[0].statement
    assert before.findings[0].severity == after.findings[0].severity


def test_not_requested():
    before = _analysis()
    after = asyncio.run(
        attach_narrative(before, include_narrative=False, settings=_enabled_settings())
    )
    assert after.narrative_status == "not_requested"
    assert after.narrative is None
    _assert_deterministic_unchanged(before, after)


def test_disabled_when_flag_off():
    before = _analysis()
    settings = _enabled_settings(helios_analyst_narrative_enabled=False)
    after = asyncio.run(
        attach_narrative(before, include_narrative=True, settings=settings)
    )
    assert after.narrative_status == "disabled"
    _assert_deterministic_unchanged(before, after)


def test_disabled_when_third_party_off():
    before = _analysis()
    settings = _enabled_settings(helios_analyst_allow_third_party=False)
    after = asyncio.run(
        attach_narrative(before, include_narrative=True, settings=settings)
    )
    assert after.narrative_status == "disabled"


def test_disabled_when_missing_key_or_model():
    before = _analysis()
    for settings in (
        _enabled_settings(openai_api_key=SecretStr("")),
        _enabled_settings(helios_analyst_model=""),
        _enabled_settings(helios_analyst_provider="anthropic"),
    ):
        after = asyncio.run(
            attach_narrative(before, include_narrative=True, settings=settings)
        )
        assert after.narrative_status == "disabled", settings


def test_complete_with_fake_provider():
    before = _analysis()
    fake = FakeNarrativeProvider(narrative=make_valid_narrative(before))
    after = asyncio.run(
        attach_narrative(
            before,
            include_narrative=True,
            settings=_enabled_settings(),
            provider=fake,
        )
    )
    assert after.narrative_status == "complete"
    assert after.narrative is not None
    assert (
        after.narrative.finding_explanations[0].evidence_id
        == before.findings[0].evidence_id
    )
    assert fake.calls == 1
    _assert_deterministic_unchanged(before, after)


def test_failed_on_timeout_and_invalid_id():
    before = _analysis()
    timeout = FakeNarrativeProvider(error=NarrativeTimeoutError("timeout"))
    after = asyncio.run(
        attach_narrative(
            before,
            include_narrative=True,
            settings=_enabled_settings(),
            provider=timeout,
        )
    )
    assert after.narrative_status == "failed"
    assert after.narrative is None
    _assert_deterministic_unchanged(before, after)

    bad = FakeNarrativeProvider(
        narrative=ProviderNarrative(
            summary="Bad",
            finding_explanations=[
                NarrativeFindingExplanation(
                    evidence_id="fake_123",
                    explanation="Invented",
                    remediation="Consider reviewing.",
                )
            ],
            caveats=[],
        )
    )
    after = asyncio.run(
        attach_narrative(
            before, include_narrative=True, settings=_enabled_settings(), provider=bad
        )
    )
    assert after.narrative_status == "failed"
    assert after.narrative is None


def test_openai_provider_retries_once_on_rate_limit():
    calls = {"n": 0}

    class Flaky(OpenAINarrativeProvider):
        def __init__(self):
            super().__init__(
                api_key="sk-test",
                model="gpt-4o-mini",
                timeout_seconds=5,
                max_output_tokens=100,
            )

        async def _call_once(self, bundle):
            calls["n"] += 1
            if calls["n"] == 1:
                raise NarrativeRateLimitError("rate")
            return make_valid_narrative(_analysis())

    before = _analysis()
    after = asyncio.run(
        attach_narrative(
            before,
            include_narrative=True,
            settings=_enabled_settings(),
            provider=Flaky(),
        )
    )
    assert calls["n"] == 2
    assert after.narrative_status == "complete"


def test_no_retry_on_invalid_output():
    calls = {"n": 0}

    class Once(OpenAINarrativeProvider):
        def __init__(self):
            super().__init__(
                api_key="sk-test",
                model="gpt-4o-mini",
                timeout_seconds=5,
                max_output_tokens=100,
            )

        async def _call_once(self, bundle):
            calls["n"] += 1
            from app.analyst_narrative.provider import NarrativeInvalidOutputError

            raise NarrativeInvalidOutputError("bad")

    before = _analysis()
    after = asyncio.run(
        attach_narrative(
            before,
            include_narrative=True,
            settings=_enabled_settings(),
            provider=Once(),
        )
    )
    assert calls["n"] == 1
    assert after.narrative_status == "failed"


def test_config_snapshot_hides_secrets():
    settings = _enabled_settings()
    snap = resolve_narrative_config(settings)
    assert "sk-test" not in repr(snap)
    assert "sk-test" not in repr(settings)
    assert snap.api_key_configured is True


def test_invalid_numeric_bounds_rejected():
    with pytest.raises(Exception):
        Settings(helios_analyst_timeout_seconds=0)
    with pytest.raises(Exception):
        Settings(helios_analyst_max_findings=0)
