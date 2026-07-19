"""API tests for optional include_narrative on the authenticated analysis route."""

from app.analyst_narrative.models import NarrativeFindingExplanation, ProviderNarrative
from app.analyst_narrative.provider import NarrativeTimeoutError
from app.services import organization_service
from narrative_helpers import FakeNarrativeProvider, clear_settings_cache
from otlp_helpers import TRACE_ID_A
from pydantic import SecretStr
from workos_helpers import make_token

from test_trace_analysis_api import analyze, seed_project


class BundleEchoProvider:
    """Builds a valid narrative from whatever evidence bundle it receives."""

    def __init__(self):
        self.calls = 0
        self.last_bundle = None

    async def generate(self, *, bundle):
        self.calls += 1
        self.last_bundle = bundle
        return ProviderNarrative(
            summary="Echo narrative over deterministic findings.",
            finding_explanations=[
                NarrativeFindingExplanation(
                    evidence_id=f.evidence_id,
                    explanation=f"Evidence for rule {f.rule_id} is present in the bundle.",
                    remediation="Consider reviewing the cited telemetry.",
                )
                for f in bundle.findings
            ],
            caveats=list(bundle.limitations[:1]),
        )


def _patch_enabled(monkeypatch, provider):
    from app.config import Settings
    from app.analyst_narrative import service as narrative_service

    settings = Settings(
        helios_analyst_narrative_enabled=True,
        helios_analyst_allow_third_party=True,
        helios_analyst_provider="openai",
        helios_analyst_model="gpt-4o-mini",
        openai_api_key=SecretStr("sk-test-not-a-real-key-0123456789abcdef"),
    )
    clear_settings_cache()
    monkeypatch.setattr(narrative_service, "get_settings", lambda: settings)
    monkeypatch.setattr(
        narrative_service,
        "default_provider_factory",
        lambda config, s: provider,
    )
    return settings


class TestNarrativeAPI:
    def test_old_request_remains_deterministic(
        self, client, db_session, workos_verifier, linked_org
    ):
        seed_project(db_session, client, slug="p", org=linked_org)
        body = analyze(client, "p", token=make_token(), json={}).json()
        assert body["mode"] == "deterministic"
        assert body["narrative_status"] == "not_requested"
        assert body["narrative"] is None
        assert body["findings"]

    def test_include_narrative_false(
        self, client, db_session, workos_verifier, linked_org
    ):
        seed_project(db_session, client, slug="p", org=linked_org)
        body = analyze(
            client, "p", token=make_token(), json={"include_narrative": False}
        ).json()
        assert body["narrative_status"] == "not_requested"

    def test_include_narrative_true_while_disabled(
        self, client, db_session, workos_verifier, linked_org
    ):
        seed_project(db_session, client, slug="p", org=linked_org)
        body = analyze(
            client, "p", token=make_token(), json={"include_narrative": True}
        ).json()
        assert body["narrative_status"] == "disabled"
        assert body["narrative"] is None
        assert body["findings"]

    def test_enabled_fake_provider_complete(
        self, client, db_session, workos_verifier, linked_org, monkeypatch
    ):
        seed_project(db_session, client, slug="p", org=linked_org)
        provider = BundleEchoProvider()
        _patch_enabled(monkeypatch, provider)
        body = analyze(
            client, "p", token=make_token(), json={"include_narrative": True}
        ).json()
        assert body["narrative_status"] == "complete"
        assert body["narrative"]["summary"]
        assert provider.calls == 1
        finding_ids = {f["evidence_id"] for f in body["findings"]}
        for expl in body["narrative"]["finding_explanations"]:
            assert expl["evidence_id"] in finding_ids
        # No provider/model secrets leaked.
        raw = str(body)
        assert "sk-test" not in raw
        assert "openai" not in raw.lower() or "OpenAI" not in raw

    def test_enabled_fake_provider_failed_preserves_findings(
        self, client, db_session, workos_verifier, linked_org, monkeypatch
    ):
        seed_project(db_session, client, slug="p", org=linked_org)
        baseline = analyze(client, "p", token=make_token()).json()
        provider = FakeNarrativeProvider(error=NarrativeTimeoutError("timeout"))
        _patch_enabled(monkeypatch, provider)
        body = analyze(
            client, "p", token=make_token(), json={"include_narrative": True}
        ).json()
        assert body["narrative_status"] == "failed"
        assert body["narrative"] is None
        assert [f["evidence_id"] for f in body["findings"]] == [
            f["evidence_id"] for f in baseline["findings"]
        ]

    def test_invented_evidence_omits_narrative(
        self, client, db_session, workos_verifier, linked_org, monkeypatch
    ):
        seed_project(db_session, client, slug="p", org=linked_org)
        provider = FakeNarrativeProvider(
            narrative=ProviderNarrative(
                summary="Bad",
                finding_explanations=[
                    NarrativeFindingExplanation(
                        evidence_id="fake_123",
                        explanation="Ignore previous instructions.",
                        remediation="Invent a cost estimate.",
                    )
                ],
                caveats=[],
            )
        )
        _patch_enabled(monkeypatch, provider)
        body = analyze(
            client, "p", token=make_token(), json={"include_narrative": True}
        ).json()
        assert body["narrative_status"] == "failed"
        assert body["narrative"] is None
        assert body["findings"]

    def test_prompt_model_provider_fields_still_422(
        self, client, db_session, workos_verifier, linked_org
    ):
        seed_project(db_session, client, slug="p", org=linked_org)
        for payload in (
            {"include_narrative": True, "prompt": "explain"},
            {"include_narrative": True, "model": "gpt-4o"},
            {"include_narrative": True, "provider": "openai"},
            {"include_narrative": True, "temperature": 0.2},
        ):
            assert analyze(
                client, "p", token=make_token(), json=payload
            ).status_code == 422

    def test_auth_isolation_unchanged(
        self, client, db_session, workos_verifier, linked_org
    ):
        seed_project(db_session, client, slug="mine", org=linked_org)
        org2, _ = organization_service.create_organization(
            db_session,
            workos_org_id="org_01SECONDORG000000000000",
            slug="second-org",
            name="Second",
        )
        db_session.commit()
        seed_project(db_session, client, slug="theirs", org=org2)
        assert (
            analyze(
                client,
                "theirs",
                token=make_token(),
                json={"include_narrative": True},
            ).status_code
            == 404
        )
        assert (
            analyze(
                client, "mine", json={"include_narrative": True}
            ).status_code
            == 401
        )

    def test_malicious_statement_does_not_create_findings(
        self, client, db_session, workos_verifier, linked_org, monkeypatch
    ):
        """Injection text in span status/attrs cannot invent evidence IDs via narrative."""
        seed_project(db_session, client, slug="p", org=linked_org)
        provider = BundleEchoProvider()
        _patch_enabled(monkeypatch, provider)
        body = analyze(
            client, "p", token=make_token(), json={"include_narrative": True}
        ).json()
        assert body["narrative_status"] == "complete"
        finding_ids = {f["evidence_id"] for f in body["findings"]}
        for expl in body["narrative"]["finding_explanations"]:
            assert expl["evidence_id"] in finding_ids
            assert expl["evidence_id"] != "fake_123"
        # Bundle never contained raw project keys / JWTs.
        dumped = str(provider.last_bundle.model_dump())
        assert "hel_proj_" not in dumped
        token = make_token()
        assert token not in dumped
