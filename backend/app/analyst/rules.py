"""Deterministic single-trace analysis rules (ruleset single-trace-v1)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from typing import Any
from uuid import UUID

from app.analyst.evidence import build_finding
from app.analyst.hierarchy import SpanNode, TraceHierarchy
from app.analyst.models import Category, Confidence, Finding, Severity
from app.analyst.redaction import (
    bound_string,
    has_model_data,
    has_token_data,
    is_model_like,
    is_tool_like,
    model_group_key,
    read_token_total,
    sanitize_supporting_attributes,
    span_type,
    tool_identity,
)
from app.analyst.thresholds import (
    LATENCY_CONCENTRATION_ERROR,
    LATENCY_CONCENTRATION_WARN,
    MAX_STATUS_MESSAGE_LEN,
    REPEATED_SIBLING_MIN_COUNT,
    SERIAL_MIN_PARENT_FRACTION,
    SERIAL_MIN_SIBLINGS,
    SERIAL_OVERLAP_TOLERANCE_MS,
    SERIAL_WARN_PARENT_FRACTION,
)
from app.models_otel import STATUS_CODE_ERROR
from app.otel_genai_attributes import INPUT_TOKEN_KEYS, OUTPUT_TOKEN_KEYS

RuleFn = Callable[[UUID, str, dict[str, Any], TraceHierarchy], list[Finding]]


def _safe_status_message(node: SpanNode) -> str | None:
    return bound_string(node.status_message, max_len=MAX_STATUS_MESSAGE_LEN)


def rule_error_span(
    project_id: UUID,
    trace_id: str,
    _trace: dict[str, Any],
    hierarchy: TraceHierarchy,
) -> list[Finding]:
    findings: list[Finding] = []
    for span_id in hierarchy.ordered_span_ids:
        node = hierarchy.nodes[span_id]
        if node.status_code != STATUS_CODE_ERROR:
            continue
        msg = _safe_status_message(node)
        # Do not interpolate status_message into the statement (untrusted text).
        statement = (
            f"Span '{node.name}' ({span_id}) recorded OTel status ERROR "
            f"with duration {node.duration_ms:.3f}ms"
            + ("; a status message is recorded on the span." if msg else ".")
        )
        supporting = sanitize_supporting_attributes(
            node.attributes,
            extra={"name": node.name, "status_code": node.status_code},
        )
        if msg is not None:
            supporting["status_message"] = msg
        findings.append(
            build_finding(
                rule_id="error_span",
                project_id=project_id,
                trace_id=trace_id,
                span_ids=[span_id],
                severity=Severity.ERROR,
                confidence=Confidence.HIGH,
                category=Category.RELIABILITY,
                statement=statement,
                metric_name="span.status_code",
                observed_value=STATUS_CODE_ERROR,
                source_start_time=node.start_time,
                source_end_time=node.end_time,
                supporting_attributes=supporting,
            )
        )
    return findings


def rule_failing_child_transition(
    project_id: UUID,
    trace_id: str,
    _trace: dict[str, Any],
    hierarchy: TraceHierarchy,
) -> list[Finding]:
    findings: list[Finding] = []
    for span_id in hierarchy.ordered_span_ids:
        child = hierarchy.nodes[span_id]
        if child.status_code != STATUS_CODE_ERROR:
            continue
        if child.is_orphan or child.parent_span_id is None:
            continue
        parent = hierarchy.nodes.get(child.parent_span_id)
        if parent is None:
            continue
        if parent.status_code == STATUS_CODE_ERROR:
            continue
        statement = (
            f"Child span '{child.name}' ({child.span_id}) has ERROR status while "
            f"parent '{parent.name}' ({parent.span_id}) does not "
            f"(parent status_code={parent.status_code})."
        )
        findings.append(
            build_finding(
                rule_id="failing_child_transition",
                project_id=project_id,
                trace_id=trace_id,
                span_ids=[parent.span_id, child.span_id],
                severity=Severity.ERROR,
                confidence=Confidence.HIGH,
                category=Category.RELIABILITY,
                statement=statement,
                metric_name="span.failing_child_transition",
                observed_value={
                    "parent_status_code": parent.status_code,
                    "child_status_code": child.status_code,
                    "child_duration_ms": round(child.duration_ms, 3),
                },
                source_start_time=child.start_time,
                source_end_time=child.end_time,
                supporting_attributes=sanitize_supporting_attributes(
                    child.attributes,
                    extra={
                        "name": child.name,
                        "status_code": child.status_code,
                    },
                ),
            )
        )
    return findings


def rule_latency_concentration(
    project_id: UUID,
    trace_id: str,
    trace: dict[str, Any],
    hierarchy: TraceHierarchy,
) -> list[Finding]:
    try:
        trace_duration = float(trace.get("duration_ms") or 0.0)
    except (TypeError, ValueError):
        trace_duration = 0.0
    if trace_duration <= 0 or not hierarchy.nodes:
        return []

    root_ids = set(hierarchy.roots)
    candidates = [
        hierarchy.nodes[sid]
        for sid in hierarchy.ordered_span_ids
        if sid not in root_ids
    ]
    if not candidates:
        return []

    longest = max(candidates, key=lambda n: (n.duration_ms, n.span_id))
    fraction = longest.duration_ms / trace_duration
    if fraction + 1e-12 < LATENCY_CONCENTRATION_WARN:
        return []

    severity = (
        Severity.ERROR
        if fraction + 1e-12 >= LATENCY_CONCENTRATION_ERROR
        else Severity.WARNING
    )
    pct = round(fraction * 100, 2)
    statement = (
        f"Non-root span '{longest.name}' ({longest.span_id}) accounted for "
        f"{pct}% of trace duration ({longest.duration_ms:.3f}ms of "
        f"{trace_duration:.3f}ms)."
    )
    return [
        build_finding(
            rule_id="latency_concentration",
            project_id=project_id,
            trace_id=trace_id,
            span_ids=[longest.span_id],
            severity=severity,
            confidence=Confidence.HIGH,
            category=Category.PERFORMANCE,
            statement=statement,
            metric_name="span.duration_fraction_of_trace",
            observed_value=pct,
            baseline_value=round(trace_duration, 3),
            source_start_time=longest.start_time,
            source_end_time=longest.end_time,
            supporting_attributes=sanitize_supporting_attributes(
                longest.attributes, extra={"name": longest.name}
            ),
        )
    ]


def rule_repeated_sibling_tool_calls(
    project_id: UUID,
    trace_id: str,
    _trace: dict[str, Any],
    hierarchy: TraceHierarchy,
) -> list[Finding]:
    findings: list[Finding] = []
    # Group tool-like children by (parent_id, tool_identity).
    groups: dict[tuple[str, str], list[SpanNode]] = defaultdict(list)
    for parent_id, child_ids in hierarchy.children.items():
        for child_id in child_ids:
            node = hierarchy.nodes[child_id]
            if not is_tool_like(node.attributes):
                continue
            identity = tool_identity(node.attributes, span_name=node.name)
            groups[(parent_id, identity)].append(node)

    for (parent_id, identity), members in sorted(
        groups.items(), key=lambda item: (item[0][0], item[0][1])
    ):
        if len(members) < REPEATED_SIBLING_MIN_COUNT:
            continue
        members = sorted(members, key=lambda n: (n.start_time, n.span_id))
        span_ids = [m.span_id for m in members]
        total_duration = sum(m.duration_ms for m in members)
        statement = (
            f"Observed {len(members)} sibling tool-like spans with identity "
            f"'{identity}' under parent {parent_id} "
            f"(combined duration {total_duration:.3f}ms)."
        )
        findings.append(
            build_finding(
                rule_id="repeated_sibling_tool_calls",
                project_id=project_id,
                trace_id=trace_id,
                span_ids=span_ids,
                severity=Severity.WARNING,
                confidence=Confidence.MEDIUM,
                category=Category.EFFICIENCY,
                statement=statement,
                metric_name="tool.repeated_sibling_count",
                observed_value=len(members),
                baseline_value=identity,
                source_start_time=members[0].start_time,
                source_end_time=members[-1].end_time,
                supporting_attributes=sanitize_supporting_attributes(
                    members[0].attributes,
                    extra={"name": members[0].name},
                ),
            )
        )
    return findings


def rule_repeated_sibling_model_calls(
    project_id: UUID,
    trace_id: str,
    _trace: dict[str, Any],
    hierarchy: TraceHierarchy,
) -> list[Finding]:
    findings: list[Finding] = []
    groups: dict[tuple[str, str, str], list[SpanNode]] = defaultdict(list)
    for parent_id, child_ids in hierarchy.children.items():
        for child_id in child_ids:
            node = hierarchy.nodes[child_id]
            if not is_model_like(node.attributes):
                continue
            model, operation = model_group_key(node.attributes, span_name=node.name)
            groups[(parent_id, model, operation)].append(node)

    for (parent_id, model, operation), members in sorted(
        groups.items(), key=lambda item: item[0]
    ):
        if len(members) < REPEATED_SIBLING_MIN_COUNT:
            continue
        members = sorted(members, key=lambda n: (n.start_time, n.span_id))
        span_ids = [m.span_id for m in members]
        total_duration = sum(m.duration_ms for m in members)
        input_tokens = 0
        output_tokens = 0
        saw_tokens = False
        for m in members:
            inn = read_token_total(m.attributes, INPUT_TOKEN_KEYS)
            out = read_token_total(m.attributes, OUTPUT_TOKEN_KEYS)
            if inn is not None:
                input_tokens += inn
                saw_tokens = True
            if out is not None:
                output_tokens += out
                saw_tokens = True
        model_label = model or "unspecified-model"
        statement = (
            f"Observed {len(members)} sibling model-like spans "
            f"(model='{model_label}', operation='{operation}') under parent "
            f"{parent_id} (combined duration {total_duration:.3f}ms"
        )
        if saw_tokens:
            statement += (
                f", recorded tokens in={input_tokens} out={output_tokens}"
            )
        statement += ")."
        observed: dict[str, Any] = {
            "count": len(members),
            "model": model or None,
            "operation": operation,
            "total_duration_ms": round(total_duration, 3),
        }
        if saw_tokens:
            observed["input_tokens"] = input_tokens
            observed["output_tokens"] = output_tokens
        findings.append(
            build_finding(
                rule_id="repeated_sibling_model_calls",
                project_id=project_id,
                trace_id=trace_id,
                span_ids=span_ids,
                severity=Severity.WARNING,
                confidence=Confidence.MEDIUM,
                category=Category.EFFICIENCY,
                statement=statement,
                metric_name="model.repeated_sibling_count",
                observed_value=observed,
                source_start_time=members[0].start_time,
                source_end_time=members[-1].end_time,
                supporting_attributes=sanitize_supporting_attributes(
                    members[0].attributes, extra={"name": members[0].name}
                ),
            )
        )
    return findings


def _intervals_serial(nodes: Sequence[SpanNode]) -> bool:
    """True when intervals do not materially overlap (sorted by start)."""
    ordered = sorted(nodes, key=lambda n: (n.start_time, n.span_id))
    if any(n.duration_ms <= 0 for n in ordered):
        return False
    prev_end_ms = None
    for node in ordered:
        start_ms = node.start_time.timestamp() * 1000.0
        end_ms = node.end_time.timestamp() * 1000.0
        if end_ms < start_ms:
            return False
        if prev_end_ms is not None:
            # Overlap if this start is materially before previous end.
            if start_ms + SERIAL_OVERLAP_TOLERANCE_MS < prev_end_ms:
                return False
        prev_end_ms = max(prev_end_ms or end_ms, end_ms)
    return True


def rule_serial_sibling_operations(
    project_id: UUID,
    trace_id: str,
    _trace: dict[str, Any],
    hierarchy: TraceHierarchy,
) -> list[Finding]:
    findings: list[Finding] = []
    for parent_id, child_ids in sorted(hierarchy.children.items()):
        parent = hierarchy.nodes.get(parent_id)
        if parent is None or parent.duration_ms <= 0:
            continue
        relevant = [
            hierarchy.nodes[cid]
            for cid in child_ids
            if is_tool_like(hierarchy.nodes[cid].attributes)
            or is_model_like(hierarchy.nodes[cid].attributes)
        ]
        if len(relevant) < SERIAL_MIN_SIBLINGS:
            continue
        if not _intervals_serial(relevant):
            continue
        combined = sum(n.duration_ms for n in relevant)
        fraction = combined / parent.duration_ms
        if fraction + 1e-12 < SERIAL_MIN_PARENT_FRACTION:
            continue
        severity = (
            Severity.WARNING
            if fraction + 1e-12 >= SERIAL_WARN_PARENT_FRACTION
            else Severity.INFO
        )
        relevant = sorted(relevant, key=lambda n: (n.start_time, n.span_id))
        span_ids = [n.span_id for n in relevant]
        pct = round(fraction * 100, 2)
        statement = (
            f"Observed {len(relevant)} tool/model sibling spans under parent "
            f"'{parent.name}' ({parent_id}) executing serially without material "
            f"overlap, consuming {pct}% of the parent duration "
            f"({combined:.3f}ms of {parent.duration_ms:.3f}ms). "
            f"This does not prove the work can be parallelized."
        )
        findings.append(
            build_finding(
                rule_id="serial_sibling_operations",
                project_id=project_id,
                trace_id=trace_id,
                span_ids=span_ids,
                severity=severity,
                confidence=Confidence.MEDIUM,
                category=Category.PERFORMANCE,
                statement=statement,
                metric_name="span.serial_sibling_parent_fraction",
                observed_value=pct,
                baseline_value=round(parent.duration_ms, 3),
                source_start_time=relevant[0].start_time,
                source_end_time=relevant[-1].end_time,
                supporting_attributes=sanitize_supporting_attributes(
                    parent.attributes, extra={"name": parent.name}
                ),
            )
        )
    return findings


def rule_missing_genai_telemetry(
    project_id: UUID,
    trace_id: str,
    _trace: dict[str, Any],
    hierarchy: TraceHierarchy,
) -> list[Finding]:
    findings: list[Finding] = []
    for span_id in hierarchy.ordered_span_ids:
        node = hierarchy.nodes[span_id]
        if not is_model_like(node.attributes):
            continue
        missing: list[str] = []
        if not has_model_data(node.attributes):
            missing.append("gen_ai.request.model/gen_ai.response.model")
        if not has_token_data(node.attributes):
            missing.append("gen_ai.usage.input_tokens/gen_ai.usage.output_tokens")
        if not missing:
            continue
        confidence = (
            Confidence.HIGH
            if span_type(node.attributes) == "llm"
            else Confidence.MEDIUM
        )
        statement = (
            f"Model-like span '{node.name}' ({span_id}) is missing "
            f"{', '.join(missing)}."
        )
        findings.append(
            build_finding(
                rule_id="missing_genai_telemetry",
                project_id=project_id,
                trace_id=trace_id,
                span_ids=[span_id],
                severity=Severity.INFO,
                confidence=confidence,
                category=Category.INSTRUMENTATION,
                statement=statement,
                metric_name="gen_ai.missing_fields",
                observed_value=missing,
                source_start_time=node.start_time,
                source_end_time=node.end_time,
                supporting_attributes=sanitize_supporting_attributes(
                    node.attributes,
                    extra={
                        "name": node.name,
                        "scope_name": node.scope_name or "",
                    },
                ),
            )
        )
    return findings


def rule_orphan_span_parent(
    project_id: UUID,
    trace_id: str,
    _trace: dict[str, Any],
    hierarchy: TraceHierarchy,
) -> list[Finding]:
    findings: list[Finding] = []
    for span_id in hierarchy.orphans:
        node = hierarchy.nodes[span_id]
        statement = (
            f"Span '{node.name}' ({span_id}) references parent_span_id "
            f"'{node.parent_span_id}' which is not present in this trace."
        )
        findings.append(
            build_finding(
                rule_id="orphan_span_parent",
                project_id=project_id,
                trace_id=trace_id,
                span_ids=[span_id],
                severity=Severity.INFO,
                confidence=Confidence.HIGH,
                category=Category.INSTRUMENTATION,
                statement=statement,
                metric_name="span.orphan_parent",
                observed_value=node.parent_span_id,
                source_start_time=node.start_time,
                source_end_time=node.end_time,
                supporting_attributes=sanitize_supporting_attributes(
                    node.attributes, extra={"name": node.name}
                ),
            )
        )
    return findings


def rule_cyclic_span_hierarchy(
    project_id: UUID,
    trace_id: str,
    _trace: dict[str, Any],
    hierarchy: TraceHierarchy,
) -> list[Finding]:
    findings: list[Finding] = []
    for cycle in hierarchy.cycles:
        span_ids = list(cycle)
        statement = (
            "Detected a cyclic span hierarchy involving span IDs: "
            + ", ".join(span_ids)
            + "."
        )
        first = hierarchy.nodes[span_ids[0]]
        findings.append(
            build_finding(
                rule_id="cyclic_span_hierarchy",
                project_id=project_id,
                trace_id=trace_id,
                span_ids=span_ids,
                severity=Severity.WARNING,
                confidence=Confidence.HIGH,
                category=Category.INSTRUMENTATION,
                statement=statement,
                metric_name="span.hierarchy_cycle",
                observed_value=span_ids,
                source_start_time=first.start_time,
                source_end_time=first.end_time,
                supporting_attributes={},
            )
        )
    return findings


RULE_REGISTRY: dict[str, RuleFn] = {
    "error_span": rule_error_span,
    "failing_child_transition": rule_failing_child_transition,
    "latency_concentration": rule_latency_concentration,
    "repeated_sibling_tool_calls": rule_repeated_sibling_tool_calls,
    "repeated_sibling_model_calls": rule_repeated_sibling_model_calls,
    "serial_sibling_operations": rule_serial_sibling_operations,
    "missing_genai_telemetry": rule_missing_genai_telemetry,
    "orphan_span_parent": rule_orphan_span_parent,
    "cyclic_span_hierarchy": rule_cyclic_span_hierarchy,
}

DEFAULT_RULE_IDS: tuple[str, ...] = tuple(RULE_REGISTRY.keys())
