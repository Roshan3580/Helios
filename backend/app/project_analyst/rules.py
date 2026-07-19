"""Deterministic project-window rules (ruleset project-window-v1).

Every rule is a pure function over :class:`ProjectRuleContext` — no database
session, no network access, no clock reads. Statements are factual window
comparisons and never claim causation, deployment attribution, or root-cause
certainty.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from app.project_analyst.evidence import build_project_finding
from app.project_analyst.models import (
    Category,
    Confidence,
    ProjectEntityType,
    ProjectFinding,
    ProjectWindow,
    ProjectWindowEvidence,
    Severity,
)
from app.project_analyst.thresholds import (
    CONCENTRATION_ERROR_MIN_ERROR_TRACES,
    CONCENTRATION_ERROR_SHARE,
    CONCENTRATION_MIN_ERROR_TRACES,
    CONCENTRATION_MIN_SERVICES_OBSERVED,
    CONCENTRATION_WARN_SHARE,
    ERROR_CLUSTER_ERROR_OCCURRENCES,
    ERROR_CLUSTER_MIN_DISTINCT_TRACES,
    ERROR_CLUSTER_MIN_OCCURRENCES,
    ERROR_RATE_ERROR_PP_INCREASE,
    ERROR_RATE_MIN_PP_INCREASE,
    ERROR_RATE_MIN_RELATIVE_FACTOR,
    ERROR_RATE_MIN_TRACES_PER_WINDOW,
    ERROR_RATE_ZERO_BASELINE_MIN_ERRORS,
    GENAI_GAP_INFO_RATE,
    GENAI_GAP_MIN_MODEL_LIKE_SPANS,
    GENAI_GAP_WARNING_RATE,
    LATENCY_ERROR_FACTOR,
    LATENCY_MIN_ABSOLUTE_INCREASE_MS,
    LATENCY_MIN_FACTOR,
    LATENCY_MIN_SAMPLE_PER_WINDOW,
    OUTLIER_ERROR_MAX_FACTOR,
    OUTLIER_MIN_CURRENT_TRACES,
    OUTLIER_MIN_DURATION_MS,
    OUTLIER_P95_FACTOR,
    REGRESSION_HIGH_CONFIDENCE_MIN_SAMPLE,
    TOKEN_HIGH_CONFIDENCE_MIN_SPANS,
    TOKEN_MIN_ABSOLUTE_INCREASE,
    TOKEN_MIN_FACTOR,
    TOKEN_MIN_SPANS_PER_WINDOW,
)

# Tolerance for floating-point threshold comparisons on derived rates/ratios.
_EPS = 1e-9


@dataclass(frozen=True)
class ProjectRuleContext:
    project_id: UUID
    current_window: ProjectWindow
    baseline_window: ProjectWindow
    evidence: ProjectWindowEvidence


ProjectRuleFn = Callable[[ProjectRuleContext], list[ProjectFinding]]


def _pct(rate: float) -> float:
    return round(rate * 100, 2)


def rule_service_error_rate_regression(ctx: ProjectRuleContext) -> list[ProjectFinding]:
    findings: list[ProjectFinding] = []
    for svc in ctx.evidence.current_services:
        base = ctx.evidence.baseline_services.get(svc.service_name)
        if svc.trace_count < ERROR_RATE_MIN_TRACES_PER_WINDOW:
            continue
        if base is None or base.trace_count < ERROR_RATE_MIN_TRACES_PER_WINDOW:
            continue
        cur_rate = svc.error_trace_count / svc.trace_count
        base_rate = base.error_trace_count / base.trace_count
        increase = cur_rate - base_rate
        if increase + _EPS < ERROR_RATE_MIN_PP_INCREASE:
            continue
        if base_rate > 0:
            if cur_rate + _EPS < ERROR_RATE_MIN_RELATIVE_FACTOR * base_rate:
                continue
        elif svc.error_trace_count < ERROR_RATE_ZERO_BASELINE_MIN_ERRORS:
            continue
        severity = (
            Severity.ERROR
            if increase + _EPS >= ERROR_RATE_ERROR_PP_INCREASE
            else Severity.WARNING
        )
        confidence = (
            Confidence.HIGH
            if svc.trace_count >= REGRESSION_HIGH_CONFIDENCE_MIN_SAMPLE
            and base.trace_count >= REGRESSION_HIGH_CONFIDENCE_MIN_SAMPLE
            else Confidence.MEDIUM
        )
        statement = (
            f"Service '{svc.service_name}' trace error rate was "
            f"{_pct(cur_rate)}% ({svc.error_trace_count}/{svc.trace_count}) in the "
            f"current window versus {_pct(base_rate)}% "
            f"({base.error_trace_count}/{base.trace_count}) in the baseline window, "
            f"an increase of {_pct(increase)} percentage points. "
            f"This window comparison does not establish a cause."
        )
        findings.append(
            build_project_finding(
                rule_id="service_error_rate_regression",
                project_id=ctx.project_id,
                current_window=ctx.current_window,
                baseline_window=ctx.baseline_window,
                severity=severity,
                confidence=confidence,
                category=Category.RELIABILITY,
                statement=statement,
                metric_name="service.trace_error_rate",
                observed_value=round(cur_rate, 6),
                baseline_value=round(base_rate, 6),
                entity_type=ProjectEntityType.SERVICE,
                entity_label=svc.service_name,
                supporting_traces=ctx.evidence.error_examples_by_service.get(
                    svc.service_name, []
                ),
                sample_size={
                    "current_traces": svc.trace_count,
                    "baseline_traces": base.trace_count,
                },
                supporting_values={
                    "current_error_traces": svc.error_trace_count,
                    "baseline_error_traces": base.error_trace_count,
                    "increase_percentage_points": _pct(increase),
                },
            )
        )
    return findings


def _latency_regression(
    ctx: ProjectRuleContext,
    *,
    rule_id: str,
    entity_type: ProjectEntityType,
    entity_label: str,
    metric_name: str,
    current_sample: int,
    baseline_sample: int,
    current_p50: float | None,
    baseline_p50: float | None,
    current_p95: float | None,
    baseline_p95: float | None,
    sample_noun: str,
    examples,
) -> ProjectFinding | None:
    if current_sample < LATENCY_MIN_SAMPLE_PER_WINDOW:
        return None
    if baseline_sample < LATENCY_MIN_SAMPLE_PER_WINDOW:
        return None
    if current_p95 is None or baseline_p95 is None or current_p95 <= 0:
        return None
    increase = current_p95 - baseline_p95
    if increase + _EPS < LATENCY_MIN_ABSOLUTE_INCREASE_MS:
        return None
    if baseline_p95 > 0:
        factor = current_p95 / baseline_p95
        if factor + _EPS < LATENCY_MIN_FACTOR:
            return None
        factor_text = f"{factor:.2f}x the baseline p95"
        is_error = factor + _EPS >= LATENCY_ERROR_FACTOR
    else:
        factor = None
        factor_text = "with a baseline p95 of 0ms"
        is_error = True
    severity = Severity.ERROR if is_error else Severity.WARNING
    confidence = (
        Confidence.HIGH
        if current_sample >= REGRESSION_HIGH_CONFIDENCE_MIN_SAMPLE
        and baseline_sample >= REGRESSION_HIGH_CONFIDENCE_MIN_SAMPLE
        else Confidence.MEDIUM
    )
    noun = "Service" if entity_type is ProjectEntityType.SERVICE else "Model"
    statement = (
        f"{noun} '{entity_label}' p95 {sample_noun} duration was "
        f"{current_p95:.3f}ms in the current window versus {baseline_p95:.3f}ms in "
        f"the baseline window ({factor_text}, +{increase:.3f}ms). This comparison "
        f"describes observed latency and does not establish a performance root cause."
    )
    supporting_values = {
        "current_p50_duration_ms": current_p50,
        "baseline_p50_duration_ms": baseline_p50,
        "absolute_increase_ms": round(increase, 3),
    }
    if factor is not None:
        supporting_values["p95_factor"] = round(factor, 4)
    return build_project_finding(
        rule_id=rule_id,
        project_id=ctx.project_id,
        current_window=ctx.current_window,
        baseline_window=ctx.baseline_window,
        severity=severity,
        confidence=confidence,
        category=Category.PERFORMANCE,
        statement=statement,
        metric_name=metric_name,
        observed_value=round(current_p95, 3),
        baseline_value=round(baseline_p95, 3),
        entity_type=entity_type,
        entity_label=entity_label,
        supporting_traces=examples,
        sample_size={
            f"current_{sample_noun}s": current_sample,
            f"baseline_{sample_noun}s": baseline_sample,
        },
        supporting_values=supporting_values,
    )


def rule_service_latency_regression(ctx: ProjectRuleContext) -> list[ProjectFinding]:
    findings: list[ProjectFinding] = []
    for svc in ctx.evidence.current_services:
        base = ctx.evidence.baseline_services.get(svc.service_name)
        if base is None:
            continue
        finding = _latency_regression(
            ctx,
            rule_id="service_latency_regression",
            entity_type=ProjectEntityType.SERVICE,
            entity_label=svc.service_name,
            metric_name="service.p95_trace_duration_ms",
            current_sample=svc.trace_count,
            baseline_sample=base.trace_count,
            current_p50=svc.p50_duration_ms,
            baseline_p50=base.p50_duration_ms,
            current_p95=svc.p95_duration_ms,
            baseline_p95=base.p95_duration_ms,
            sample_noun="trace",
            examples=ctx.evidence.slow_examples_by_service.get(svc.service_name, []),
        )
        if finding is not None:
            findings.append(finding)
    return findings


def rule_model_latency_regression(ctx: ProjectRuleContext) -> list[ProjectFinding]:
    findings: list[ProjectFinding] = []
    for model in ctx.evidence.current_models:
        base = ctx.evidence.baseline_models.get(model.model)
        if base is None:
            continue
        finding = _latency_regression(
            ctx,
            rule_id="model_latency_regression",
            entity_type=ProjectEntityType.MODEL,
            entity_label=model.model,
            metric_name="model.p95_span_duration_ms",
            current_sample=model.span_count,
            baseline_sample=base.span_count,
            current_p50=model.p50_duration_ms,
            baseline_p50=base.p50_duration_ms,
            current_p95=model.p95_duration_ms,
            baseline_p95=base.p95_duration_ms,
            sample_noun="span",
            examples=ctx.evidence.slow_examples_by_model.get(model.model, []),
        )
        if finding is not None:
            findings.append(finding)
    return findings


def rule_model_token_usage_regression(ctx: ProjectRuleContext) -> list[ProjectFinding]:
    findings: list[ProjectFinding] = []
    for model in ctx.evidence.current_models:
        base = ctx.evidence.baseline_models.get(model.model)
        if model.token_span_count < TOKEN_MIN_SPANS_PER_WINDOW:
            continue
        if base is None or base.token_span_count < TOKEN_MIN_SPANS_PER_WINDOW:
            continue
        cur_avg = model.total_tokens / model.token_span_count
        base_avg = base.total_tokens / base.token_span_count
        increase = cur_avg - base_avg
        if increase + _EPS < TOKEN_MIN_ABSOLUTE_INCREASE:
            continue
        if base_avg > 0 and cur_avg + _EPS < TOKEN_MIN_FACTOR * base_avg:
            continue
        confidence = (
            Confidence.HIGH
            if model.token_span_count >= TOKEN_HIGH_CONFIDENCE_MIN_SPANS
            and base.token_span_count >= TOKEN_HIGH_CONFIDENCE_MIN_SPANS
            else Confidence.MEDIUM
        )
        statement = (
            f"Model '{model.model}' averaged {cur_avg:.1f} recorded total tokens "
            f"(input + output) per token-reporting span in the current window versus "
            f"{base_avg:.1f} in the baseline window (+{increase:.1f}). Only spans "
            f"with recorded token attributes are compared; no cost is derived."
        )
        findings.append(
            build_project_finding(
                rule_id="model_token_usage_regression",
                project_id=ctx.project_id,
                current_window=ctx.current_window,
                baseline_window=ctx.baseline_window,
                severity=Severity.WARNING,
                confidence=confidence,
                category=Category.EFFICIENCY,
                statement=statement,
                metric_name="model.avg_total_tokens_per_span",
                observed_value=round(cur_avg, 3),
                baseline_value=round(base_avg, 3),
                entity_type=ProjectEntityType.MODEL,
                entity_label=model.model,
                supporting_traces=ctx.evidence.token_examples_by_model.get(
                    model.model, []
                ),
                sample_size={
                    "current_token_spans": model.token_span_count,
                    "baseline_token_spans": base.token_span_count,
                },
                supporting_values={
                    "current_input_tokens": round(model.input_tokens, 1),
                    "current_output_tokens": round(model.output_tokens, 1),
                    "absolute_increase_tokens": round(increase, 1),
                },
            )
        )
    return findings


def rule_trace_latency_outliers(ctx: ProjectRuleContext) -> list[ProjectFinding]:
    current = ctx.evidence.current
    if current.trace_count < OUTLIER_MIN_CURRENT_TRACES:
        return []
    p95 = current.p95_duration_ms
    if p95 is None or p95 <= 0:
        return []
    if ctx.evidence.outlier_count <= 0:
        return []
    examples = ctx.evidence.outlier_examples
    max_duration = examples[0].duration_ms if examples else 0.0
    severity = (
        Severity.ERROR
        if max_duration + _EPS >= OUTLIER_ERROR_MAX_FACTOR * p95
        else Severity.WARNING
    )
    threshold_ms = max(OUTLIER_P95_FACTOR * p95, OUTLIER_MIN_DURATION_MS)
    count = ctx.evidence.outlier_count
    statement = (
        f"{count} trace{'s' if count != 1 else ''} in the current window lasted at "
        f"least {threshold_ms:.3f}ms (at least {OUTLIER_P95_FACTOR:g}x the current "
        f"project p95 of {p95:.3f}ms and at least {OUTLIER_MIN_DURATION_MS:g}ms); "
        f"the slowest lasted {max_duration:.3f}ms. Outliers describe the duration "
        f"distribution, not a specific cause."
    )
    return [
        build_project_finding(
            rule_id="trace_latency_outliers",
            project_id=ctx.project_id,
            current_window=ctx.current_window,
            baseline_window=ctx.baseline_window,
            severity=severity,
            confidence=Confidence.HIGH,
            category=Category.PERFORMANCE,
            statement=statement,
            metric_name="trace.duration_outlier_count",
            observed_value=count,
            baseline_value=round(p95, 3),
            entity_type=ProjectEntityType.PROJECT,
            entity_label="project",
            supporting_traces=examples,
            sample_size={"current_traces": current.trace_count},
            supporting_values={
                "current_p50_duration_ms": current.p50_duration_ms,
                "current_p95_duration_ms": p95,
                "outlier_threshold_ms": round(threshold_ms, 3),
                "max_outlier_duration_ms": round(max_duration, 3),
            },
        )
    ]


def rule_recurring_error_cluster(ctx: ProjectRuleContext) -> list[ProjectFinding]:
    findings: list[ProjectFinding] = []
    for cluster in ctx.evidence.error_clusters:
        if cluster.occurrence_count < ERROR_CLUSTER_MIN_OCCURRENCES:
            continue
        if cluster.distinct_trace_count < ERROR_CLUSTER_MIN_DISTINCT_TRACES:
            continue
        severity = (
            Severity.ERROR
            if cluster.occurrence_count >= ERROR_CLUSTER_ERROR_OCCURRENCES
            else Severity.WARNING
        )
        confidence = (
            Confidence.HIGH
            if cluster.exception_type or cluster.normalized_message
            else Confidence.MEDIUM
        )
        # The normalized message stays in entity/supporting evidence only; the
        # statement interpolates just the span name (matching the single-trace
        # engine's handling of untrusted status text).
        statement = (
            f"Observed {cluster.occurrence_count} ERROR spans across "
            f"{cluster.distinct_trace_count} distinct traces sharing a common "
            f"error signature on span '{cluster.span_name}' in the current window. "
            f"A shared signature does not establish that these errors have the "
            f"same underlying cause."
        )
        supporting_values = {
            "distinct_trace_count": cluster.distinct_trace_count,
            "signature_span_name": cluster.span_name,
        }
        if cluster.exception_type:
            supporting_values["signature_exception_type"] = cluster.exception_type
        if cluster.normalized_message:
            supporting_values["signature_normalized_message"] = (
                cluster.normalized_message
            )
        findings.append(
            build_project_finding(
                rule_id="recurring_error_cluster",
                project_id=ctx.project_id,
                current_window=ctx.current_window,
                baseline_window=ctx.baseline_window,
                severity=severity,
                confidence=confidence,
                category=Category.RELIABILITY,
                statement=statement,
                metric_name="error_span.cluster_occurrences",
                observed_value=cluster.occurrence_count,
                entity_type=ProjectEntityType.ERROR_SIGNATURE,
                entity_label=cluster.signature_label,
                supporting_traces=cluster.supporting_traces,
                supporting_span_ids=cluster.supporting_span_ids,
                sample_size={"current_error_spans": cluster.occurrence_count},
                supporting_values=supporting_values,
            )
        )
    return findings


def rule_genai_instrumentation_gap(ctx: ProjectRuleContext) -> list[ProjectFinding]:
    genai = ctx.evidence.genai
    total = genai.model_like_span_count
    if total < GENAI_GAP_MIN_MODEL_LIKE_SPANS:
        return []
    missing_model_rate = genai.missing_model_count / total
    missing_token_rate = genai.missing_token_count / total
    worst = max(missing_model_rate, missing_token_rate)
    if worst + _EPS < GENAI_GAP_INFO_RATE:
        return []
    severity = (
        Severity.WARNING
        if worst + _EPS >= GENAI_GAP_WARNING_RATE
        else Severity.INFO
    )
    confidence = (
        Confidence.HIGH
        if genai.explicitly_classified_count >= total
        else Confidence.MEDIUM
    )
    statement = (
        f"Of {total} model-like spans in the current window, "
        f"{genai.missing_model_count} ({_pct(missing_model_rate)}%) are missing "
        f"model identity and {genai.missing_token_count} "
        f"({_pct(missing_token_rate)}%) are missing both input and output token "
        f"telemetry. Missing attributes limit model-level analysis."
    )
    return [
        build_project_finding(
            rule_id="genai_instrumentation_gap",
            project_id=ctx.project_id,
            current_window=ctx.current_window,
            baseline_window=ctx.baseline_window,
            severity=severity,
            confidence=confidence,
            category=Category.INSTRUMENTATION,
            statement=statement,
            metric_name="gen_ai.instrumentation_gap_rate",
            observed_value=round(worst, 6),
            entity_type=ProjectEntityType.INSTRUMENTATION,
            entity_label="gen_ai telemetry",
            supporting_traces=genai.supporting_traces,
            supporting_span_ids=genai.supporting_span_ids,
            sample_size={"current_model_like_spans": total},
            supporting_values={
                "missing_model_count": genai.missing_model_count,
                "missing_model_rate": round(missing_model_rate, 6),
                "missing_token_count": genai.missing_token_count,
                "missing_token_rate": round(missing_token_rate, 6),
                "explicitly_classified_count": genai.explicitly_classified_count,
            },
        )
    ]


def rule_error_concentration_by_service(
    ctx: ProjectRuleContext,
) -> list[ProjectFinding]:
    current = ctx.evidence.current
    if current.error_trace_count < CONCENTRATION_MIN_ERROR_TRACES:
        return []
    if ctx.evidence.coverage.services_observed < CONCENTRATION_MIN_SERVICES_OBSERVED:
        return []
    candidates = [s for s in ctx.evidence.current_services if s.error_trace_count > 0]
    if not candidates:
        return []
    top = min(candidates, key=lambda s: (-s.error_trace_count, s.service_name))
    share = top.error_trace_count / current.error_trace_count
    if share + _EPS < CONCENTRATION_WARN_SHARE:
        return []
    severity = (
        Severity.ERROR
        if share + _EPS >= CONCENTRATION_ERROR_SHARE
        and top.error_trace_count >= CONCENTRATION_ERROR_MIN_ERROR_TRACES
        else Severity.WARNING
    )
    statement = (
        f"Service '{top.service_name}' accounted for {_pct(share)}% of the "
        f"project's error traces ({top.error_trace_count} of "
        f"{current.error_trace_count}) in the current window. Concentration "
        f"describes where errors occurred, not what caused them."
    )
    return [
        build_project_finding(
            rule_id="error_concentration_by_service",
            project_id=ctx.project_id,
            current_window=ctx.current_window,
            baseline_window=ctx.baseline_window,
            severity=severity,
            confidence=Confidence.HIGH,
            category=Category.RELIABILITY,
            statement=statement,
            metric_name="service.error_trace_share",
            observed_value=round(share, 6),
            entity_type=ProjectEntityType.SERVICE,
            entity_label=top.service_name,
            supporting_traces=ctx.evidence.error_examples_by_service.get(
                top.service_name, []
            ),
            sample_size={
                "current_error_traces": current.error_trace_count,
                "services_observed": ctx.evidence.coverage.services_observed,
            },
            supporting_values={
                "service_error_traces": top.error_trace_count,
                "project_error_traces": current.error_trace_count,
            },
        )
    ]


PROJECT_RULE_REGISTRY: dict[str, ProjectRuleFn] = {
    "service_error_rate_regression": rule_service_error_rate_regression,
    "service_latency_regression": rule_service_latency_regression,
    "model_latency_regression": rule_model_latency_regression,
    "model_token_usage_regression": rule_model_token_usage_regression,
    "trace_latency_outliers": rule_trace_latency_outliers,
    "recurring_error_cluster": rule_recurring_error_cluster,
    "genai_instrumentation_gap": rule_genai_instrumentation_gap,
    "error_concentration_by_service": rule_error_concentration_by_service,
}

PROJECT_DEFAULT_RULE_IDS: tuple[str, ...] = tuple(PROJECT_RULE_REGISTRY.keys())
