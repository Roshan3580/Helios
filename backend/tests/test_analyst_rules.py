"""Per-rule positive, negative, and boundary tests."""

from app.analyst import analyze_trace
from app.analyst.models import Confidence, Severity
from analyst_fixtures import PROJECT_ID, span, trace_detail


def _findings(detail, rule_id: str):
    result = analyze_trace(
        project_id=PROJECT_ID, trace_detail=detail, rules=[rule_id]
    )
    return result.findings


class TestErrorSpan:
    def test_triggers_on_status_error_only(self):
        detail = trace_detail(
            [
                span("root", name="root"),
                span(
                    "e",
                    name="fail",
                    parent_span_id="root",
                    status_code=2,
                    status_message="timeout",
                ),
                span("ok", name="ok", parent_span_id="root", status_code=1),
            ]
        )
        findings = _findings(detail, "error_span")
        assert len(findings) == 1
        assert findings[0].severity == Severity.ERROR
        assert findings[0].confidence == Confidence.HIGH
        assert findings[0].span_ids == ["e"]
        assert "timeout" not in findings[0].statement
        assert findings[0].supporting_attributes.get("status_message") == "timeout"


class TestFailingChildTransition:
    def test_error_child_under_healthy_parent(self):
        detail = trace_detail(
            [
                span("root", name="root", status_code=1),
                span("c", name="child", parent_span_id="root", status_code=2),
            ]
        )
        findings = _findings(detail, "failing_child_transition")
        assert len(findings) == 1
        assert set(findings[0].span_ids) == {"root", "c"}

    def test_error_child_under_error_parent_no_transition(self):
        detail = trace_detail(
            [
                span("root", name="root", status_code=2),
                span("c", name="child", parent_span_id="root", status_code=2),
            ]
        )
        assert _findings(detail, "failing_child_transition") == []

    def test_orphan_error_child_skipped(self):
        detail = trace_detail(
            [span("c", name="child", parent_span_id="missing", status_code=2)]
        )
        assert _findings(detail, "failing_child_transition") == []


class TestLatencyConcentration:
    def _case(self, child_ms: float, trace_ms: float = 1000.0):
        return trace_detail(
            [
                span("root", name="root", duration_ms=trace_ms),
                span(
                    "child",
                    name="child",
                    parent_span_id="root",
                    start_offset_ms=0,
                    duration_ms=child_ms,
                ),
            ],
            duration_ms=trace_ms,
        )

    def test_boundaries(self):
        assert _findings(self._case(499.9), "latency_concentration") == []
        warn = _findings(self._case(500.0), "latency_concentration")
        assert len(warn) == 1 and warn[0].severity == Severity.WARNING
        warn2 = _findings(self._case(799.9), "latency_concentration")
        assert len(warn2) == 1 and warn2[0].severity == Severity.WARNING
        err = _findings(self._case(800.0), "latency_concentration")
        assert len(err) == 1 and err[0].severity == Severity.ERROR

    def test_does_not_flag_root_only(self):
        detail = trace_detail([span("root", name="root", duration_ms=1000)], duration_ms=1000)
        assert _findings(detail, "latency_concentration") == []


class TestRepeatedTools:
    def test_two_vs_three_and_parent_isolation(self):
        two = trace_detail(
            [
                span("root", name="root", duration_ms=100),
                span(
                    "t1",
                    name="tool",
                    parent_span_id="root",
                    start_offset_ms=0,
                    attributes={"helios.span.type": "tool", "tool.name": "search"},
                ),
                span(
                    "t2",
                    name="tool",
                    parent_span_id="root",
                    start_offset_ms=10,
                    attributes={"helios.span.type": "tool", "tool.name": "search"},
                ),
            ]
        )
        assert _findings(two, "repeated_sibling_tool_calls") == []

        three = trace_detail(
            [
                span("root", name="root", duration_ms=100),
                *[
                    span(
                        f"t{i}",
                        name="tool",
                        parent_span_id="root",
                        start_offset_ms=i * 10,
                        attributes={"tool.name": "search"},
                    )
                    for i in range(3)
                ],
            ]
        )
        findings = _findings(three, "repeated_sibling_tool_calls")
        assert len(findings) == 1
        assert findings[0].observed_value == 3
        assert findings[0].severity == Severity.WARNING

        # Different parents do not group.
        split = trace_detail(
            [
                span("r1", name="r1", duration_ms=50),
                span("r2", name="r2", start_offset_ms=0, duration_ms=50),
                span(
                    "a1",
                    parent_span_id="r1",
                    start_offset_ms=1,
                    attributes={"tool.name": "search"},
                ),
                span(
                    "a2",
                    parent_span_id="r1",
                    start_offset_ms=2,
                    attributes={"tool.name": "search"},
                ),
                span(
                    "b1",
                    parent_span_id="r2",
                    start_offset_ms=1,
                    attributes={"tool.name": "search"},
                ),
            ]
        )
        assert _findings(split, "repeated_sibling_tool_calls") == []

    def test_different_identities_do_not_group(self):
        detail = trace_detail(
            [
                span("root", name="root", duration_ms=100),
                span(
                    "t1",
                    parent_span_id="root",
                    start_offset_ms=0,
                    attributes={"tool.name": "a"},
                ),
                span(
                    "t2",
                    parent_span_id="root",
                    start_offset_ms=10,
                    attributes={"tool.name": "b"},
                ),
                span(
                    "t3",
                    parent_span_id="root",
                    start_offset_ms=20,
                    attributes={"tool.name": "a"},
                ),
            ]
        )
        assert _findings(detail, "repeated_sibling_tool_calls") == []


class TestRepeatedModels:
    def test_model_grouping_and_no_token_fabrication(self):
        detail = trace_detail(
            [
                span("root", name="root", duration_ms=100),
                *[
                    span(
                        f"m{i}",
                        name="chat",
                        parent_span_id="root",
                        start_offset_ms=i * 10,
                        duration_ms=5,
                        attributes={
                            "helios.span.type": "llm",
                            "gen_ai.request.model": "gpt-4o",
                            "gen_ai.operation.name": "chat",
                            "gen_ai.usage.input_tokens": 10,
                            "gen_ai.usage.output_tokens": 2,
                        },
                    )
                    for i in range(3)
                ],
            ]
        )
        findings = _findings(detail, "repeated_sibling_model_calls")
        assert len(findings) == 1
        observed = findings[0].observed_value
        assert observed["count"] == 3
        assert observed["input_tokens"] == 30
        assert observed["output_tokens"] == 6
        # No 75/25 fabrication beyond recorded values.
        assert observed["input_tokens"] != int(36 * 0.75)


class TestSerialSiblings:
    def test_non_overlap_vs_overlap(self):
        serial = trace_detail(
            [
                span("root", name="root", duration_ms=100),
                span(
                    "t1",
                    parent_span_id="root",
                    start_offset_ms=0,
                    duration_ms=30,
                    attributes={"helios.span.type": "tool", "tool.name": "a"},
                ),
                span(
                    "t2",
                    parent_span_id="root",
                    start_offset_ms=30,
                    duration_ms=30,
                    attributes={"helios.span.type": "tool", "tool.name": "b"},
                ),
                span(
                    "t3",
                    parent_span_id="root",
                    start_offset_ms=60,
                    duration_ms=30,
                    attributes={"helios.span.type": "llm", "gen_ai.request.model": "m"},
                ),
            ]
        )
        findings = _findings(serial, "serial_sibling_operations")
        assert len(findings) == 1
        assert findings[0].severity == Severity.WARNING  # 90% >= 85%
        assert "serially" in findings[0].statement
        assert "does not prove" in findings[0].statement

        overlapping = trace_detail(
            [
                span("root", name="root", duration_ms=100),
                span(
                    "t1",
                    parent_span_id="root",
                    start_offset_ms=0,
                    duration_ms=40,
                    attributes={"tool.name": "a"},
                ),
                span(
                    "t2",
                    parent_span_id="root",
                    start_offset_ms=10,
                    duration_ms=40,
                    attributes={"tool.name": "b"},
                ),
                span(
                    "t3",
                    parent_span_id="root",
                    start_offset_ms=20,
                    duration_ms=40,
                    attributes={"tool.name": "c"},
                ),
            ]
        )
        assert _findings(overlapping, "serial_sibling_operations") == []


class TestMissingGenai:
    def test_sparse_model_and_token_telemetry(self):
        detail = trace_detail(
            [
                span(
                    "llm1",
                    name="chat",
                    attributes={"helios.span.type": "llm"},
                ),
                span(
                    "llm2",
                    name="chat",
                    start_offset_ms=1,
                    attributes={
                        "gen_ai.operation.name": "chat",
                        "gen_ai.request.model": "gpt-4o",
                    },
                ),
                span(
                    "llm3",
                    name="chat",
                    start_offset_ms=2,
                    attributes={
                        "helios.span.type": "llm",
                        "gen_ai.request.model": "gpt-4o",
                        "gen_ai.usage.input_tokens": 1,
                        "gen_ai.usage.output_tokens": 1,
                    },
                ),
            ]
        )
        findings = _findings(detail, "missing_genai_telemetry")
        ids = {f.span_ids[0] for f in findings}
        assert ids == {"llm1", "llm2"}
        by_id = {f.span_ids[0]: f for f in findings}
        assert by_id["llm1"].confidence == Confidence.HIGH
        assert by_id["llm2"].confidence == Confidence.MEDIUM


class TestOrphanAndCycle:
    def test_orphan_and_cycle_rules(self):
        orphan_detail = trace_detail(
            [span("x", name="x", parent_span_id="nope")]
        )
        orphans = _findings(orphan_detail, "orphan_span_parent")
        assert len(orphans) == 1
        assert orphans[0].category.value == "instrumentation"

        cycle_detail = trace_detail(
            [
                span("a", name="a", parent_span_id="b"),
                span("b", name="b", parent_span_id="a", start_offset_ms=1),
            ]
        )
        cycles = _findings(cycle_detail, "cyclic_span_hierarchy")
        assert len(cycles) == 1
        assert set(cycles[0].span_ids) == {"a", "b"}
        # Dedup: running twice still one finding per analysis.
        assert len(_findings(cycle_detail, "cyclic_span_hierarchy")) == 1
