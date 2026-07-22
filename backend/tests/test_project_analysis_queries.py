"""Bounded evidence-query behavior for project-window analysis.

Uses direct ORM seeding with deterministic timestamps (fixed ``AS_OF``) so
window membership, project scoping, aggregation accuracy, bounded examples,
and truncation metadata can be asserted exactly.
"""

from datetime import timedelta

import pytest

from app.project_analyst import queries as queries_module
from app.project_analyst import runner as runner_module
from app.project_analyst.evidence import (
    make_project_evidence_id,
    normalize_exception_type,
    normalize_status_message,
)
from app.project_analyst.models import ProjectEntityType, ProjectWindow
from app.project_analyst.queries import collect_project_evidence
from app.project_analyst.runner import analyze_project_window, resolve_windows
from app.services import api_key_service

from project_analysis_helpers import (
    AS_OF,
    llm_attributes,
    make_service_traces,
    make_trace,
)

HOURS = 24
CURRENT_WINDOW, BASELINE_WINDOW = resolve_windows(hours=HOURS, as_of=AS_OF)
CURRENT_START = CURRENT_WINDOW.start
BASELINE_START = BASELINE_WINDOW.start


@pytest.fixture()
def project(db_session):
    project = api_key_service.get_or_create_project(db_session, slug="pw-proj")
    db_session.commit()
    return project


def evidence_for(db_session, project, *, hours: int = HOURS):
    current, baseline = resolve_windows(hours=hours, as_of=AS_OF)
    db_session.commit()
    return collect_project_evidence(
        db_session,
        project_id=project.id,
        current_window=current,
        baseline_window=baseline,
    )


class TestWindowBoundaries:
    def test_half_open_current_window(self, db_session, project):
        # Inclusive lower bound: exactly at current start belongs to current.
        make_trace(db_session, project=project, start=CURRENT_START)
        # Exclusive upper bound: exactly at as_of is excluded entirely.
        make_trace(db_session, project=project, start=AS_OF)
        # Just inside the upper bound.
        make_trace(
            db_session, project=project, start=AS_OF - timedelta(microseconds=1)
        )
        evidence = evidence_for(db_session, project)
        assert evidence.current.trace_count == 2
        assert evidence.baseline.trace_count == 0

    def test_boundary_between_baseline_and_current(self, db_session, project):
        # Exactly at current start == baseline end: current, never baseline.
        make_trace(db_session, project=project, start=CURRENT_START)
        # Just before current start: baseline.
        make_trace(
            db_session,
            project=project,
            start=CURRENT_START - timedelta(microseconds=1),
        )
        # Exactly at baseline start: baseline (inclusive).
        make_trace(db_session, project=project, start=BASELINE_START)
        # Just before baseline start: outside both windows.
        make_trace(
            db_session,
            project=project,
            start=BASELINE_START - timedelta(microseconds=1),
        )
        evidence = evidence_for(db_session, project)
        assert evidence.current.trace_count == 1
        assert evidence.baseline.trace_count == 2

    def test_resolved_windows_are_exact(self):
        current, baseline = resolve_windows(hours=7, as_of=AS_OF)
        assert current.end == AS_OF
        assert current.start == AS_OF - timedelta(hours=7)
        assert baseline.end == current.start
        assert baseline.start == AS_OF - timedelta(hours=14)


class TestProjectScoping:
    def test_same_trace_ids_in_other_project_never_mix(self, db_session, project):
        other = api_key_service.get_or_create_project(db_session, slug="pw-other")
        db_session.commit()
        shared_id = "ab" * 16
        make_trace(
            db_session,
            project=project,
            trace_id=shared_id,
            start=CURRENT_START + timedelta(hours=1),
            error=True,
        )
        make_trace(
            db_session,
            project=other,
            trace_id=shared_id,
            start=CURRENT_START + timedelta(hours=1),
        )
        for _ in range(3):
            make_trace(
                db_session,
                project=other,
                start=CURRENT_START + timedelta(hours=2),
                error=True,
                service="other-svc",
            )
        evidence = evidence_for(db_session, project)
        assert evidence.current.trace_count == 1
        assert evidence.current.error_trace_count == 1
        assert evidence.coverage.services_observed == 1
        assert all(
            s.service_name != "other-svc" for s in evidence.current_services
        )


class TestAggregates:
    def test_counts_and_percentiles(self, db_session, project):
        durations = [100.0, 200.0, 300.0, 400.0]
        for index, duration in enumerate(durations):
            make_trace(
                db_session,
                project=project,
                start=CURRENT_START + timedelta(minutes=index + 1),
                duration_ms=duration,
                error=index == 0,
            )
        make_trace(
            db_session,
            project=project,
            start=BASELINE_START + timedelta(minutes=1),
            duration_ms=50.0,
        )
        evidence = evidence_for(db_session, project)
        assert evidence.current.trace_count == 4
        assert evidence.current.error_trace_count == 1
        assert evidence.current.span_count == 4
        assert evidence.baseline.trace_count == 1
        assert evidence.baseline.span_count == 1
        # percentile_cont: p50 of [100,200,300,400] = 250, p95 = 385.
        assert evidence.current.p50_duration_ms == pytest.approx(250.0, abs=0.01)
        assert evidence.current.p95_duration_ms == pytest.approx(385.0, abs=0.01)

    def test_service_aggregation_and_baseline_lookup(self, db_session, project):
        make_service_traces(
            db_session,
            project=project,
            service="svc-a",
            window_start=CURRENT_START,
            total=3,
            errors=1,
        )
        make_service_traces(
            db_session,
            project=project,
            service="svc-b",
            window_start=CURRENT_START,
            total=2,
        )
        make_service_traces(
            db_session,
            project=project,
            service="svc-a",
            window_start=BASELINE_START,
            total=4,
            errors=2,
        )
        evidence = evidence_for(db_session, project)
        by_name = {s.service_name: s for s in evidence.current_services}
        assert by_name["svc-a"].trace_count == 3
        assert by_name["svc-a"].error_trace_count == 1
        assert by_name["svc-b"].trace_count == 2
        assert evidence.baseline_services["svc-a"].trace_count == 4
        assert evidence.baseline_services["svc-a"].error_trace_count == 2
        assert "svc-b" not in evidence.baseline_services
        assert evidence.coverage.services_observed == 2

    def test_empty_project(self, db_session, project):
        evidence = evidence_for(db_session, project)
        assert evidence.current.trace_count == 0
        assert evidence.baseline.trace_count == 0
        assert evidence.current.p50_duration_ms is None
        assert evidence.current_services == []
        assert evidence.current_models == []
        assert evidence.error_clusters == []
        assert evidence.outlier_count == 0
        assert evidence.coverage.current_sample_sparse is True
        assert evidence.coverage.baseline_sample_sparse is True

    def test_baseline_only_data(self, db_session, project):
        make_service_traces(
            db_session,
            project=project,
            service="svc-a",
            window_start=BASELINE_START,
            total=5,
        )
        evidence = evidence_for(db_session, project)
        assert evidence.current.trace_count == 0
        assert evidence.baseline.trace_count == 5
        assert evidence.current_services == []


class TestModelExtraction:
    def test_request_model_takes_precedence(self, db_session, project):
        make_trace(
            db_session,
            project=project,
            start=CURRENT_START + timedelta(minutes=1),
            spans=[
                {
                    "name": "chat",
                    "attributes": llm_attributes(
                        model="gpt-req", response_model="gpt-resp"
                    ),
                },
                {
                    "name": "chat",
                    "attributes": llm_attributes(
                        model=None, response_model="gpt-resp-only"
                    ),
                },
            ],
        )
        evidence = evidence_for(db_session, project)
        models = {m.model for m in evidence.current_models}
        assert models == {"gpt-req", "gpt-resp-only"}

    def test_token_extraction_and_malformed_values_ignored(self, db_session, project):
        make_trace(
            db_session,
            project=project,
            start=CURRENT_START + timedelta(minutes=1),
            spans=[
                {
                    "name": "chat",
                    "attributes": llm_attributes(
                        model="gpt-x", input_tokens=100, output_tokens=50
                    ),
                },
                {
                    # Malformed: string / object token values must be ignored.
                    "name": "chat",
                    "attributes": llm_attributes(
                        model="gpt-x",
                        input_tokens="not-a-number",
                        output_tokens={"nested": True},
                    ),
                },
                {
                    # Missing token values: span is not token-attributed.
                    "name": "chat",
                    "attributes": llm_attributes(model="gpt-x"),
                },
                {
                    # Output only: still token-attributed; missing input is not
                    # estimated (contributes 0 to the total).
                    "name": "chat",
                    "attributes": llm_attributes(model="gpt-x", output_tokens=25),
                },
            ],
        )
        evidence = evidence_for(db_session, project)
        model = next(m for m in evidence.current_models if m.model == "gpt-x")
        assert model.span_count == 4
        assert model.token_span_count == 2
        assert model.input_tokens == 100
        assert model.output_tokens == 75
        assert model.total_tokens == 175
        assert evidence.coverage.spans_with_token_data == 2


class TestExamplesAndBounds:
    def test_error_examples_bounded_and_newest_first(self, db_session, project):
        traces = make_service_traces(
            db_session,
            project=project,
            service="svc-a",
            window_start=CURRENT_START,
            total=8,
            errors=8,
        )
        evidence = evidence_for(db_session, project)
        examples = evidence.error_examples_by_service["svc-a"]
        assert len(examples) == 5
        newest_first = sorted(traces, key=lambda t: t.start_time, reverse=True)[:5]
        assert [ref.trace_id for ref in examples] == [
            t.trace_id for t in newest_first
        ]
        for ref in examples:
            assert ref.trace_ui_path == f"/app/traces/{ref.trace_id}"
            assert ref.error_count >= 1

    def test_slow_examples_ordered_by_duration(self, db_session, project):
        for index, duration in enumerate([100.0, 900.0, 300.0, 700.0, 500.0, 50.0]):
            make_trace(
                db_session,
                project=project,
                service="svc-a",
                start=CURRENT_START + timedelta(minutes=index + 1),
                duration_ms=duration,
            )
        evidence = evidence_for(db_session, project)
        examples = evidence.slow_examples_by_service["svc-a"]
        assert [ref.duration_ms for ref in examples] == [
            900.0,
            700.0,
            500.0,
            300.0,
            100.0,
        ]

    def test_service_cap_and_truncation_flag(self, db_session, project, monkeypatch):
        monkeypatch.setattr(queries_module, "MAX_SERVICES_ANALYZED", 2)
        for name, total in (("svc-big", 4), ("svc-mid", 3), ("svc-small", 1)):
            make_service_traces(
                db_session,
                project=project,
                service=name,
                window_start=CURRENT_START,
                total=total,
            )
        evidence = evidence_for(db_session, project)
        assert [s.service_name for s in evidence.current_services] == [
            "svc-big",
            "svc-mid",
        ]
        assert evidence.services_truncated is True
        assert evidence.coverage.services_observed == 3

    def test_error_span_candidate_cap_flag(self, db_session, project, monkeypatch):
        monkeypatch.setattr(queries_module, "MAX_ERROR_SPAN_CANDIDATES", 4)
        make_trace(
            db_session,
            project=project,
            start=CURRENT_START + timedelta(minutes=1),
            spans=[
                {"name": "op.fail", "status_code": 2, "status_message": "boom"}
                for _ in range(6)
            ],
        )
        evidence = evidence_for(db_session, project)
        assert evidence.error_span_candidates_truncated is True

    def test_error_group_cap_flag(self, db_session, project, monkeypatch):
        monkeypatch.setattr(queries_module, "MAX_ERROR_GROUPS", 2)
        make_trace(
            db_session,
            project=project,
            start=CURRENT_START + timedelta(minutes=1),
            spans=[
                {"name": f"op-{i}", "status_code": 2} for i in range(4)
            ],
        )
        evidence = evidence_for(db_session, project)
        assert len(evidence.error_clusters) == 2
        assert evidence.error_groups_truncated is True


class TestErrorClustering:
    def test_signature_groups_and_counts(self, db_session, project):
        for minute in (1, 2):
            make_trace(
                db_session,
                project=project,
                start=CURRENT_START + timedelta(minutes=minute),
                spans=[
                    {
                        "name": "db.query",
                        "status_code": 2,
                        "status_message": "connection timeout after 30s (attempt 4)",
                        "attributes": {"exception.type": "TimeoutError"},
                    },
                    {
                        "name": "db.query",
                        "status_code": 2,
                        "status_message": "connection timeout after 12s (attempt 9)",
                        "attributes": {"exception.type": "TimeoutError"},
                    },
                ],
            )
        evidence = evidence_for(db_session, project)
        assert len(evidence.error_clusters) == 1
        cluster = evidence.error_clusters[0]
        assert cluster.occurrence_count == 4
        assert cluster.distinct_trace_count == 2
        assert cluster.exception_type == "TimeoutError"
        # Digit runs normalize to '#': both messages share one signature.
        assert cluster.normalized_message == "connection timeout after #s (attempt #)"
        assert len(cluster.supporting_traces) == 2
        assert len(cluster.supporting_span_ids) == 4

    def test_secret_like_tokens_redacted_from_signature(self, db_session, project):
        secret = "sk-supersecretvalue1234567890abcdefghij"
        make_trace(
            db_session,
            project=project,
            start=CURRENT_START + timedelta(minutes=1),
            spans=[
                {
                    "name": "auth.call",
                    "status_code": 2,
                    "status_message": f"denied for key {secret}",
                }
            ],
        )
        evidence = evidence_for(db_session, project)
        cluster = evidence.error_clusters[0]
        assert secret not in (cluster.normalized_message or "")
        assert secret not in cluster.signature_label
        assert "<long>" in (cluster.normalized_message or "")


class TestNormalizationHelpers:
    def test_normalize_status_message(self):
        assert normalize_status_message("timeout after 30s") == "timeout after #s"
        assert normalize_status_message("  a \n b\t c ") == "a b c"
        assert normalize_status_message("") is None
        assert normalize_status_message(None) is None
        long_token = "x" * 40
        assert normalize_status_message(f"bad {long_token}") == "bad <long>"
        bounded = normalize_status_message("word " * 40)
        assert bounded is not None and len(bounded) <= 64

    def test_normalize_exception_type(self):
        assert normalize_exception_type(" TimeoutError ") == "TimeoutError"
        assert normalize_exception_type(123) is None
        assert normalize_exception_type("") is None
        long_type = "E" * 100
        assert len(normalize_exception_type(long_type) or "") <= 64


class TestGenAiAndCoverage:
    def test_genai_gap_counts_and_examples(self, db_session, project):
        make_trace(
            db_session,
            project=project,
            start=CURRENT_START + timedelta(minutes=1),
            spans=[
                # Fully instrumented (explicit llm type + OpenAI scope).
                {
                    "name": "chat",
                    "scope_name": "opentelemetry.instrumentation.openai_v2",
                    "attributes": llm_attributes(
                        model="gpt-a", input_tokens=10, output_tokens=5,
                        span_type="llm",
                    ),
                },
                # Missing tokens only.
                {
                    "name": "chat",
                    "attributes": llm_attributes(model="gpt-a", span_type="llm"),
                },
                # Missing model identity (operation-name classified).
                {
                    "name": "chat",
                    "attributes": llm_attributes(model=None, operation="chat"),
                },
                # Tool span: never counted as model-like.
                {
                    "name": "tool.search",
                    "attributes": {"tool.name": "search"},
                },
            ],
        )
        evidence = evidence_for(db_session, project)
        genai = evidence.genai
        assert genai.model_like_span_count == 3
        assert genai.missing_model_count == 1
        assert genai.missing_token_count == 2
        assert genai.explicitly_classified_count == 2
        assert len(genai.supporting_traces) == 1
        assert len(genai.supporting_span_ids) == 2
        assert evidence.coverage.tool_like_span_count == 1
        assert evidence.coverage.spans_with_model_data == 2
        assert evidence.coverage.models_observed == 1

    def test_root_and_orphan_coverage(self, db_session, project):
        make_trace(
            db_session,
            project=project,
            start=CURRENT_START + timedelta(minutes=1),
            root_span=False,
            spans=[
                {"name": "floating", "parent_span_id": "feedfeedfeedfeed"},
            ],
        )
        make_trace(
            db_session,
            project=project,
            start=CURRENT_START + timedelta(minutes=2),
        )
        evidence = evidence_for(db_session, project)
        assert evidence.coverage.traces_without_root_span == 1
        assert evidence.coverage.orphan_span_count == 1


class TestOutlierQuery:
    def test_outlier_count_and_examples(self, db_session, project):
        # 20 traces at 100ms, one at 5000ms. p95 of 21 values stays near 100,
        # so the 5000ms trace exceeds max(2*p95, 500).
        for index in range(20):
            make_trace(
                db_session,
                project=project,
                start=CURRENT_START + timedelta(minutes=index + 1),
                duration_ms=100.0,
            )
        slow = make_trace(
            db_session,
            project=project,
            start=CURRENT_START + timedelta(minutes=30),
            duration_ms=5000.0,
        )
        evidence = evidence_for(db_session, project)
        assert evidence.outlier_count == 1
        assert evidence.outlier_examples[0].trace_id == slow.trace_id


class TestRunnerDeterminism:
    def test_same_input_same_evidence_ids(self, db_session, project):
        make_trace(
            db_session,
            project=project,
            start=CURRENT_START + timedelta(minutes=1),
            spans=[{"name": "op.fail", "status_code": 2} for _ in range(3)],
        )
        make_trace(
            db_session,
            project=project,
            start=CURRENT_START + timedelta(minutes=2),
            spans=[{"name": "op.fail", "status_code": 2}],
        )
        db_session.commit()
        first = analyze_project_window(
            db_session, project_id=project.id, hours=HOURS, as_of=AS_OF
        )
        second = analyze_project_window(
            db_session, project_id=project.id, hours=HOURS, as_of=AS_OF
        )
        assert [f.evidence_id for f in first.findings] == [
            f.evidence_id for f in second.findings
        ]
        assert first.findings, "expected at least one cluster finding"
        assert all(f.evidence_id.startswith("pev_") for f in first.findings)

    def test_evidence_id_scoped_to_project_and_window(self):
        current, baseline = resolve_windows(hours=24, as_of=AS_OF)
        import uuid

        kwargs = dict(
            rule_id="service_error_rate_regression",
            current_window=current,
            baseline_window=baseline,
            entity_type=ProjectEntityType.SERVICE,
            entity_label="svc-a",
            metric_name="service.trace_error_rate",
            observed_value=0.5,
        )
        a = make_project_evidence_id(project_id=uuid.UUID(int=1), **kwargs)
        b = make_project_evidence_id(project_id=uuid.UUID(int=2), **kwargs)
        assert a != b
        other_current, other_baseline = resolve_windows(
            hours=24, as_of=AS_OF + timedelta(hours=1)
        )
        c = make_project_evidence_id(
            project_id=uuid.UUID(int=1),
            **{
                **kwargs,
                "current_window": other_current,
                "baseline_window": other_baseline,
            },
        )
        assert a != c

    def test_findings_cap_truncation_metadata(self, db_session, project, monkeypatch):
        monkeypatch.setattr(runner_module, "MAX_PROJECT_FINDINGS", 2)
        # Four distinct clusters, each across 2 traces with 3 occurrences.
        for minute in (1, 2):
            make_trace(
                db_session,
                project=project,
                start=CURRENT_START + timedelta(minutes=minute),
                spans=[
                    {"name": f"op-{i}", "status_code": 2}
                    for i in range(4)
                    for _ in range(2 if minute == 1 else 1)
                ],
            )
        db_session.commit()
        result = analyze_project_window(
            db_session,
            project_id=project.id,
            hours=HOURS,
            as_of=AS_OF,
            rules=["recurring_error_cluster"],
        )
        assert len(result.findings) == 2
        assert result.bounds.findings_truncated is True
        assert result.bounds.max_findings == 2

    def test_stable_finding_order(self, db_session, project):
        # Two clusters with different severities: 10+ occurrences -> error,
        # 3 occurrences -> warning; error sorts first.
        for minute in (1, 2):
            make_trace(
                db_session,
                project=project,
                start=CURRENT_START + timedelta(minutes=minute),
                spans=(
                    [{"name": "big.fail", "status_code": 2} for _ in range(5)]
                    + [{"name": "small.fail", "status_code": 2}]
                    + ([{"name": "small.fail", "status_code": 2}] if minute == 1 else [])
                ),
            )
        db_session.commit()
        result = analyze_project_window(
            db_session,
            project_id=project.id,
            hours=HOURS,
            as_of=AS_OF,
            rules=["recurring_error_cluster"],
        )
        assert [f.severity.value for f in result.findings] == ["error", "warning"]
        assert result.findings[0].entity_label.startswith("span 'big.fail'")
