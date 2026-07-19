"""Threshold, sample-boundary, and severity behavior of the project rules.

Pure-function tests: evidence structures are constructed directly (no
database), matching the runner's contract that rules never touch a session.
"""

import uuid
from datetime import datetime, timezone

import pytest

from app.project_analyst.models import (
    ErrorClusterStats,
    GenAiGapStats,
    ModelWindowStats,
    ProjectCoverage,
    ProjectWindowEvidence,
    ServiceWindowStats,
    SupportingTraceRef,
    WindowAggregate,
)
from app.project_analyst.rules import (
    PROJECT_DEFAULT_RULE_IDS,
    PROJECT_RULE_REGISTRY,
    ProjectRuleContext,
    rule_error_concentration_by_service,
    rule_genai_instrumentation_gap,
    rule_model_latency_regression,
    rule_model_token_usage_regression,
    rule_recurring_error_cluster,
    rule_service_error_rate_regression,
    rule_service_latency_regression,
    rule_trace_latency_outliers,
)
from app.project_analyst.runner import resolve_windows

PROJECT_ID = uuid.UUID(int=42)
AS_OF = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)
CURRENT, BASELINE = resolve_windows(hours=24, as_of=AS_OF)


def coverage(**overrides) -> ProjectCoverage:
    values = dict(
        current_trace_count=0,
        baseline_trace_count=0,
        current_span_count=0,
        baseline_span_count=0,
        current_error_trace_count=0,
        baseline_error_trace_count=0,
        services_observed=0,
        models_observed=0,
        model_like_span_count=0,
        spans_with_model_data=0,
        spans_with_token_data=0,
        tool_like_span_count=0,
        traces_without_root_span=0,
        orphan_span_count=0,
        current_sample_sparse=False,
        baseline_sample_sparse=False,
    )
    values.update(overrides)
    return ProjectCoverage(**values)


def aggregate(**overrides) -> WindowAggregate:
    values = dict(trace_count=0, error_trace_count=0, span_count=0)
    values.update(overrides)
    return WindowAggregate(**values)


def ref(trace_id: str = "aa" * 16, **overrides) -> SupportingTraceRef:
    values = dict(
        trace_id=trace_id,
        service_name="svc-a",
        root_span_name="agent.run",
        start_time=AS_OF,
        duration_ms=100.0,
        span_count=1,
        error_count=1,
        trace_ui_path=f"/app/traces/{trace_id}",
    )
    values.update(overrides)
    return SupportingTraceRef(**values)


def context(**overrides) -> ProjectRuleContext:
    values = dict(
        current=aggregate(),
        baseline=aggregate(),
        coverage=coverage(),
    )
    values.update(overrides)
    return ProjectRuleContext(
        project_id=PROJECT_ID,
        current_window=CURRENT,
        baseline_window=BASELINE,
        evidence=ProjectWindowEvidence(**values),
    )


def service(name="svc-a", *, traces, errors=0, p50=None, p95=None) -> ServiceWindowStats:
    return ServiceWindowStats(
        service_name=name,
        trace_count=traces,
        error_trace_count=errors,
        p50_duration_ms=p50,
        p95_duration_ms=p95,
    )


def model(name="gpt-x", *, spans, p50=None, p95=None, token_spans=0, total=0.0):
    return ModelWindowStats(
        model=name,
        span_count=spans,
        p50_duration_ms=p50,
        p95_duration_ms=p95,
        token_span_count=token_spans,
        total_tokens=total,
        input_tokens=total * 0.6,
        output_tokens=total * 0.4,
    )


def error_rate_ctx(
    *, cur_traces, cur_errors, base_traces, base_errors
) -> ProjectRuleContext:
    return context(
        current_services=[
            service(traces=cur_traces, errors=cur_errors)
        ],
        baseline_services={
            "svc-a": service(traces=base_traces, errors=base_errors)
        },
        error_examples_by_service={"svc-a": [ref()]},
    )


class TestServiceErrorRateRegression:
    def test_nine_current_traces_suppressed(self):
        ctx = error_rate_ctx(cur_traces=9, cur_errors=9, base_traces=20, base_errors=0)
        assert rule_service_error_rate_regression(ctx) == []

    def test_nine_baseline_traces_suppressed(self):
        ctx = error_rate_ctx(cur_traces=20, cur_errors=20, base_traces=9, base_errors=0)
        assert rule_service_error_rate_regression(ctx) == []

    def test_missing_baseline_service_suppressed(self):
        ctx = context(
            current_services=[service(traces=20, errors=20)],
            baseline_services={},
        )
        assert rule_service_error_rate_regression(ctx) == []

    def test_ten_traces_each_window_eligible(self):
        ctx = error_rate_ctx(cur_traces=10, cur_errors=3, base_traces=10, base_errors=0)
        findings = rule_service_error_rate_regression(ctx)
        assert len(findings) == 1
        assert findings[0].severity.value == "error"  # +30pp >= 25pp

    def test_pp_increase_just_below_threshold_suppressed(self):
        # 9.99pp: current 1999/10000 = 19.99%, baseline 1000/10000 = 10%.
        ctx = error_rate_ctx(
            cur_traces=10000, cur_errors=1999, base_traces=10000, base_errors=1000
        )
        assert rule_service_error_rate_regression(ctx) == []
        # Exactly 10pp with relative factor 2.0 -> trigger.
        ctx = error_rate_ctx(
            cur_traces=100, cur_errors=20, base_traces=100, base_errors=10
        )
        assert len(rule_service_error_rate_regression(ctx)) == 1

    def test_relative_factor_below_1_5_suppressed(self):
        # 50% -> 62%: +12pp but factor 1.24 -> suppressed.
        ctx = error_rate_ctx(
            cur_traces=100, cur_errors=62, base_traces=100, base_errors=50
        )
        assert rule_service_error_rate_regression(ctx) == []

    def test_zero_baseline_requires_three_current_errors(self):
        ctx = error_rate_ctx(cur_traces=20, cur_errors=2, base_traces=20, base_errors=0)
        assert rule_service_error_rate_regression(ctx) == []
        ctx = error_rate_ctx(cur_traces=20, cur_errors=3, base_traces=20, base_errors=0)
        findings = rule_service_error_rate_regression(ctx)
        assert len(findings) == 1
        # +15pp -> warning.
        assert findings[0].severity.value == "warning"

    def test_severity_boundary_at_25pp(self):
        # 24pp -> warning.
        ctx = error_rate_ctx(
            cur_traces=100, cur_errors=34, base_traces=100, base_errors=10
        )
        assert rule_service_error_rate_regression(ctx)[0].severity.value == "warning"
        # 25pp -> error.
        ctx = error_rate_ctx(
            cur_traces=100, cur_errors=35, base_traces=100, base_errors=10
        )
        assert rule_service_error_rate_regression(ctx)[0].severity.value == "error"

    def test_confidence_boundary_at_30_traces(self):
        ctx = error_rate_ctx(
            cur_traces=29, cur_errors=15, base_traces=100, base_errors=0
        )
        assert rule_service_error_rate_regression(ctx)[0].confidence.value == "medium"
        ctx = error_rate_ctx(
            cur_traces=30, cur_errors=15, base_traces=30, base_errors=0
        )
        assert rule_service_error_rate_regression(ctx)[0].confidence.value == "high"

    def test_statement_is_factual_not_causal(self):
        ctx = error_rate_ctx(
            cur_traces=100, cur_errors=40, base_traces=100, base_errors=5
        )
        finding = rule_service_error_rate_regression(ctx)[0]
        assert "does not establish a cause" in finding.statement
        assert "deployment" not in finding.statement.lower()
        assert finding.sample_size == {"current_traces": 100, "baseline_traces": 100}
        assert finding.supporting_traces[0].trace_ui_path.startswith("/app/traces/")


def latency_ctx(*, cur_p95, base_p95, cur_n=10, base_n=10) -> ProjectRuleContext:
    return context(
        current_services=[
            service(traces=cur_n, p50=cur_p95 / 2, p95=cur_p95)
        ],
        baseline_services={
            "svc-a": service(traces=base_n, p50=base_p95 / 2, p95=base_p95)
        },
        slow_examples_by_service={"svc-a": [ref()]},
    )


class TestServiceLatencyRegression:
    def test_factor_1_49_suppressed(self):
        ctx = latency_ctx(cur_p95=298.0, base_p95=200.0)
        assert rule_service_latency_regression(ctx) == []

    def test_factor_ok_but_below_100ms_increase_suppressed(self):
        ctx = latency_ctx(cur_p95=150.0, base_p95=100.0)  # 1.5x but +50ms
        assert rule_service_latency_regression(ctx) == []

    def test_factor_1_5_and_100ms_triggers_warning(self):
        ctx = latency_ctx(cur_p95=300.0, base_p95=200.0)
        findings = rule_service_latency_regression(ctx)
        assert len(findings) == 1
        assert findings[0].severity.value == "warning"
        assert findings[0].observed_value == 300.0
        assert findings[0].baseline_value == 200.0

    def test_factor_2_triggers_error(self):
        ctx = latency_ctx(cur_p95=400.0, base_p95=200.0)
        assert rule_service_latency_regression(ctx)[0].severity.value == "error"

    def test_sample_below_ten_suppressed(self):
        ctx = latency_ctx(cur_p95=400.0, base_p95=200.0, cur_n=9)
        assert rule_service_latency_regression(ctx) == []
        ctx = latency_ctx(cur_p95=400.0, base_p95=200.0, base_n=9)
        assert rule_service_latency_regression(ctx) == []

    def test_confidence_high_at_30_per_window(self):
        ctx = latency_ctx(cur_p95=400.0, base_p95=200.0, cur_n=30, base_n=30)
        assert rule_service_latency_regression(ctx)[0].confidence.value == "high"
        ctx = latency_ctx(cur_p95=400.0, base_p95=200.0, cur_n=30, base_n=29)
        assert rule_service_latency_regression(ctx)[0].confidence.value == "medium"

    def test_statement_not_causal(self):
        ctx = latency_ctx(cur_p95=400.0, base_p95=200.0)
        statement = rule_service_latency_regression(ctx)[0].statement
        assert "does not establish a performance root cause" in statement


def model_latency_ctx(*, cur_p95, base_p95, cur_n=10, base_n=10) -> ProjectRuleContext:
    return context(
        current_models=[model(spans=cur_n, p50=cur_p95 / 2, p95=cur_p95)],
        baseline_models={"gpt-x": model(spans=base_n, p50=base_p95 / 2, p95=base_p95)},
        slow_examples_by_model={"gpt-x": [ref()]},
    )


class TestModelLatencyRegression:
    def test_thresholds(self):
        assert rule_model_latency_regression(
            model_latency_ctx(cur_p95=298.0, base_p95=200.0)
        ) == []
        assert rule_model_latency_regression(
            model_latency_ctx(cur_p95=150.0, base_p95=100.0)
        ) == []
        warning = rule_model_latency_regression(
            model_latency_ctx(cur_p95=300.0, base_p95=200.0)
        )
        assert warning[0].severity.value == "warning"
        assert warning[0].entity_type.value == "model"
        error = rule_model_latency_regression(
            model_latency_ctx(cur_p95=400.0, base_p95=200.0)
        )
        assert error[0].severity.value == "error"

    def test_span_sample_boundaries(self):
        assert rule_model_latency_regression(
            model_latency_ctx(cur_p95=400.0, base_p95=200.0, cur_n=9)
        ) == []
        assert rule_model_latency_regression(
            model_latency_ctx(cur_p95=400.0, base_p95=200.0, base_n=9)
        ) == []

    def test_unattributed_spans_never_grouped_as_unknown_model(self):
        # Evidence only ever contains model-attributed stats; a context with
        # no attributed models yields nothing regardless of raw span volume.
        ctx = context(current=aggregate(trace_count=100, span_count=1000))
        assert rule_model_latency_regression(ctx) == []


def token_ctx(
    *, cur_avg, base_avg, cur_spans=10, base_spans=10
) -> ProjectRuleContext:
    return context(
        current_models=[
            model(spans=cur_spans, token_spans=cur_spans, total=cur_avg * cur_spans)
        ],
        baseline_models={
            "gpt-x": model(
                spans=base_spans, token_spans=base_spans, total=base_avg * base_spans
            )
        },
        token_examples_by_model={"gpt-x": [ref()]},
    )


class TestModelTokenUsageRegression:
    def test_factor_1_49_suppressed(self):
        ctx = token_ctx(cur_avg=1490.0, base_avg=1000.0)
        assert rule_model_token_usage_regression(ctx) == []

    def test_factor_ok_but_below_500_increase_suppressed(self):
        ctx = token_ctx(cur_avg=450.0, base_avg=300.0)  # 1.5x but +150
        assert rule_model_token_usage_regression(ctx) == []

    def test_exact_threshold_triggers(self):
        ctx = token_ctx(cur_avg=1500.0, base_avg=1000.0)  # 1.5x and +500
        findings = rule_model_token_usage_regression(ctx)
        assert len(findings) == 1
        assert findings[0].severity.value == "warning"

    def test_span_sample_boundaries(self):
        assert rule_model_token_usage_regression(
            token_ctx(cur_avg=2000.0, base_avg=1000.0, cur_spans=9)
        ) == []
        assert rule_model_token_usage_regression(
            token_ctx(cur_avg=2000.0, base_avg=1000.0, base_spans=9)
        ) == []

    def test_confidence_boundary(self):
        high = token_ctx(cur_avg=2000.0, base_avg=1000.0, cur_spans=30, base_spans=30)
        assert rule_model_token_usage_regression(high)[0].confidence.value == "high"
        medium = token_ctx(cur_avg=2000.0, base_avg=1000.0, cur_spans=30, base_spans=29)
        assert rule_model_token_usage_regression(medium)[0].confidence.value == "medium"

    def test_no_cost_field_or_claim(self):
        finding = rule_model_token_usage_regression(
            token_ctx(cur_avg=2000.0, base_avg=1000.0)
        )[0]
        dumped = finding.model_dump()
        assert "cost" not in str(sorted(dumped["supporting_values"].keys())).lower()
        assert "no cost is derived" in finding.statement
        assert "$" not in finding.statement


def outlier_ctx(*, traces=25, p95=200.0, count=2, max_duration=800.0):
    examples = [
        ref("cc" * 16, duration_ms=max_duration, error_count=0),
        ref("dd" * 16, duration_ms=max_duration / 2, error_count=0),
    ][: max(count, 1)]
    return context(
        current=aggregate(
            trace_count=traces,
            span_count=traces,
            p50_duration_ms=p95 / 2,
            p95_duration_ms=p95,
        ),
        outlier_count=count,
        outlier_examples=examples,
    )


class TestTraceLatencyOutliers:
    def test_below_20_traces_suppressed(self):
        assert rule_trace_latency_outliers(outlier_ctx(traces=19)) == []

    def test_no_outliers_suppressed(self):
        assert rule_trace_latency_outliers(outlier_ctx(count=0)) == []

    def test_single_project_level_finding(self):
        findings = rule_trace_latency_outliers(outlier_ctx(count=2))
        assert len(findings) == 1
        assert findings[0].entity_type.value == "project"
        assert findings[0].observed_value == 2
        assert findings[0].confidence.value == "high"

    def test_severity_boundary_at_4x_p95(self):
        warning = rule_trace_latency_outliers(
            outlier_ctx(p95=200.0, max_duration=799.0)
        )
        assert warning[0].severity.value == "warning"
        error = rule_trace_latency_outliers(outlier_ctx(p95=200.0, max_duration=800.0))
        assert error[0].severity.value == "error"

    def test_examples_bounded(self):
        finding = rule_trace_latency_outliers(outlier_ctx())[0]
        assert len(finding.supporting_traces) <= 5


def cluster(
    *, occurrences, traces, exception_type="TimeoutError", message="timeout after #s"
) -> ErrorClusterStats:
    return ErrorClusterStats(
        signature_label=f"span 'op.fail' · {exception_type} · {message}",
        span_name="op.fail",
        exception_type=exception_type,
        normalized_message=message,
        occurrence_count=occurrences,
        distinct_trace_count=traces,
        supporting_traces=[ref()],
        supporting_span_ids=["ee" * 8],
    )


class TestRecurringErrorCluster:
    def test_two_occurrences_suppressed(self):
        ctx = context(error_clusters=[cluster(occurrences=2, traces=2)])
        assert rule_recurring_error_cluster(ctx) == []

    def test_three_in_single_trace_suppressed(self):
        ctx = context(error_clusters=[cluster(occurrences=3, traces=1)])
        assert rule_recurring_error_cluster(ctx) == []

    def test_three_across_two_traces_triggers(self):
        ctx = context(error_clusters=[cluster(occurrences=3, traces=2)])
        findings = rule_recurring_error_cluster(ctx)
        assert len(findings) == 1
        assert findings[0].severity.value == "warning"
        assert findings[0].confidence.value == "high"

    def test_ten_occurrences_error_severity(self):
        ctx = context(error_clusters=[cluster(occurrences=10, traces=4)])
        assert rule_recurring_error_cluster(ctx)[0].severity.value == "error"

    def test_confidence_medium_without_status_or_exception(self):
        ctx = context(
            error_clusters=[
                cluster(occurrences=4, traces=2, exception_type=None, message=None)
            ]
        )
        assert rule_recurring_error_cluster(ctx)[0].confidence.value == "medium"

    def test_no_root_cause_assertion_and_no_message_in_statement(self):
        ctx = context(
            error_clusters=[
                cluster(occurrences=4, traces=2, message="secret gateway <long>")
            ]
        )
        finding = rule_recurring_error_cluster(ctx)[0]
        assert "does not establish" in finding.statement
        assert "secret gateway" not in finding.statement
        # Normalized message remains available as structured evidence.
        assert (
            finding.supporting_values["signature_normalized_message"]
            == "secret gateway <long>"
        )


def gap_ctx(*, total, missing_model=0, missing_tokens=0, explicit=None):
    return context(
        genai=GenAiGapStats(
            model_like_span_count=total,
            missing_model_count=missing_model,
            missing_token_count=missing_tokens,
            explicitly_classified_count=total if explicit is None else explicit,
            supporting_traces=[ref()],
            supporting_span_ids=["ff" * 8],
        )
    )


class TestGenAiInstrumentationGap:
    def test_below_five_model_like_spans_suppressed(self):
        ctx = gap_ctx(total=4, missing_model=4, missing_tokens=4)
        assert rule_genai_instrumentation_gap(ctx) == []

    def test_19_99_percent_suppressed(self):
        ctx = gap_ctx(total=10000, missing_model=1999)
        assert rule_genai_instrumentation_gap(ctx) == []

    def test_20_percent_info(self):
        ctx = gap_ctx(total=10, missing_model=2)
        findings = rule_genai_instrumentation_gap(ctx)
        assert findings[0].severity.value == "info"

    def test_50_percent_warning(self):
        ctx = gap_ctx(total=10, missing_tokens=5)
        assert rule_genai_instrumentation_gap(ctx)[0].severity.value == "warning"

    def test_confidence_by_classification_basis(self):
        explicit = gap_ctx(total=10, missing_tokens=5)
        assert rule_genai_instrumentation_gap(explicit)[0].confidence.value == "high"
        heuristic = gap_ctx(total=10, missing_tokens=5, explicit=6)
        assert (
            rule_genai_instrumentation_gap(heuristic)[0].confidence.value == "medium"
        )


def concentration_ctx(
    *, project_errors, top_errors, services_observed=2, top_traces=None
):
    return context(
        current=aggregate(
            trace_count=max(project_errors * 2, 10),
            error_trace_count=project_errors,
        ),
        coverage=coverage(services_observed=services_observed),
        current_services=[
            service(
                "svc-hot",
                traces=top_traces or max(top_errors, 1),
                errors=top_errors,
            ),
            service("svc-cold", traces=10, errors=project_errors - top_errors),
        ],
        error_examples_by_service={"svc-hot": [ref()]},
    )


class TestErrorConcentrationByService:
    def test_below_five_error_traces_suppressed(self):
        ctx = concentration_ctx(project_errors=4, top_errors=4)
        assert rule_error_concentration_by_service(ctx) == []

    def test_single_service_suppressed(self):
        ctx = concentration_ctx(project_errors=10, top_errors=10, services_observed=1)
        assert rule_error_concentration_by_service(ctx) == []

    def test_69_99_percent_suppressed(self):
        # 6999/10000 = 69.99%.
        ctx = concentration_ctx(project_errors=10000, top_errors=6999)
        assert rule_error_concentration_by_service(ctx) == []

    def test_70_percent_warning(self):
        ctx = concentration_ctx(project_errors=10, top_errors=7)
        findings = rule_error_concentration_by_service(ctx)
        assert len(findings) == 1
        assert findings[0].severity.value == "warning"
        assert findings[0].entity_label == "svc-hot"

    def test_90_percent_with_10_errors_is_error(self):
        # 11/12 = 91.7% and the concentrated service has >= 10 error traces.
        ctx = concentration_ctx(project_errors=12, top_errors=11)
        assert rule_error_concentration_by_service(ctx)[0].severity.value == "error"
        # >= 90% share but fewer than 10 error traces in the service: warning.
        ctx = concentration_ctx(project_errors=10, top_errors=9)
        assert rule_error_concentration_by_service(ctx)[0].severity.value == "warning"

    def test_statement_describes_concentration_not_causation(self):
        finding = rule_error_concentration_by_service(
            concentration_ctx(project_errors=10, top_errors=8)
        )[0]
        assert "not what caused them" in finding.statement


class TestRegistry:
    def test_registry_matches_default_order(self):
        assert list(PROJECT_RULE_REGISTRY.keys()) == list(PROJECT_DEFAULT_RULE_IDS)
        assert PROJECT_DEFAULT_RULE_IDS == (
            "service_error_rate_regression",
            "service_latency_regression",
            "model_latency_regression",
            "model_token_usage_regression",
            "trace_latency_outliers",
            "recurring_error_cluster",
            "genai_instrumentation_gap",
            "error_concentration_by_service",
        )

    def test_no_forbidden_rule_families(self):
        for rule_id in PROJECT_DEFAULT_RULE_IDS:
            for forbidden in ("cost", "rag", "citation", "hallucination", "evaluation"):
                assert forbidden not in rule_id


class TestRuleIdResolution:
    def test_unknown_rule_raises_typed_error(self):
        from app.analyst.runner import AnalystValidationError
        from app.project_analyst.runner import resolve_rule_ids

        with pytest.raises(AnalystValidationError, match="cost_regression"):
            resolve_rule_ids(["cost_regression"])

    def test_duplicates_deduplicated_first_seen(self):
        from app.project_analyst.runner import resolve_rule_ids

        assert resolve_rule_ids(
            ["trace_latency_outliers", "recurring_error_cluster", "trace_latency_outliers"]
        ) == ["trace_latency_outliers", "recurring_error_cluster"]

    def test_empty_list_rejected(self):
        from app.analyst.runner import AnalystValidationError
        from app.project_analyst.runner import resolve_rule_ids

        with pytest.raises(AnalystValidationError):
            resolve_rule_ids([])

    def test_none_returns_defaults(self):
        from app.project_analyst.runner import resolve_rule_ids

        assert resolve_rule_ids(None) == list(PROJECT_DEFAULT_RULE_IDS)
