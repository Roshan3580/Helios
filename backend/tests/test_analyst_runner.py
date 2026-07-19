"""Runner behavior for the deterministic analyst engine."""

import pytest

from app.analyst import AnalystValidationError, analyze_trace
from app.analyst.runner import MANDATORY_LIMITATIONS
from app.analyst.thresholds import RULESET_VERSION
from app.schemas_v2 import OtelTraceDetailRead
from analyst_fixtures import PROJECT_ID, TRACE_ID, span, trace_detail


class TestRunner:
    def test_empty_trace(self):
        detail = trace_detail([])
        result = analyze_trace(project_id=PROJECT_ID, trace_detail=detail)
        assert result.findings == []
        assert result.coverage.total_spans == 0
        assert result.coverage.error_spans == 0
        assert result.ruleset_version == RULESET_VERSION
        assert result.limitations == list(MANDATORY_LIMITATIONS)

    def test_default_rules_and_subset(self):
        detail = trace_detail(
            [
                span("root", name="root", duration_ms=100),
                span(
                    "err",
                    name="err",
                    parent_span_id="root",
                    start_offset_ms=10,
                    duration_ms=20,
                    status_code=2,
                ),
            ]
        )
        full = analyze_trace(project_id=PROJECT_ID, trace_detail=detail)
        assert any(f.rule_id == "error_span" for f in full.findings)
        assert full.coverage.total_spans == 2
        assert full.coverage.error_spans == 1

        subset = analyze_trace(
            project_id=PROJECT_ID,
            trace_detail=detail,
            rules=["error_span"],
        )
        assert all(f.rule_id == "error_span" for f in subset.findings)
        assert len(subset.findings) == 1

    def test_unknown_rule(self):
        with pytest.raises(AnalystValidationError, match="unknown analyst rule"):
            analyze_trace(
                project_id=PROJECT_ID,
                trace_detail=trace_detail([span("root")]),
                rules=["not_a_real_rule"],
            )

    def test_pydantic_detail_accepted(self):
        detail = trace_detail(
            [
                span("root", name="root", duration_ms=50),
                span(
                    "c",
                    parent_span_id="root",
                    start_offset_ms=0,
                    duration_ms=40,
                    status_code=2,
                ),
            ],
            duration_ms=50,
        )
        model = OtelTraceDetailRead.model_validate(detail)
        result = analyze_trace(project_id=PROJECT_ID, trace_detail=model)
        assert result.trace_id == TRACE_ID
        assert result.project_id == PROJECT_ID

    def test_identical_inputs_identical_findings(self):
        detail = trace_detail(
            [
                span("root", name="root", duration_ms=100),
                span(
                    "child",
                    parent_span_id="root",
                    start_offset_ms=0,
                    duration_ms=80,
                    attributes={"helios.span.type": "llm"},
                ),
            ],
            duration_ms=100,
        )
        a = analyze_trace(project_id=PROJECT_ID, trace_detail=detail)
        b = analyze_trace(project_id=PROJECT_ID, trace_detail=detail)
        assert [f.model_dump(exclude={"ruleset_version"}) for f in a.findings] == [
            f.model_dump(exclude={"ruleset_version"}) for f in b.findings
        ]

    def test_malformed_attributes_do_not_fail(self):
        detail = trace_detail(
            [
                span(
                    "root",
                    name="root",
                    attributes={
                        "gen_ai.usage.input_tokens": {"nested": True},
                        "gen_ai.request.model": ["not", "a", "string"],
                        "helios.span.type": "llm",
                    },
                )
            ]
        )
        result = analyze_trace(project_id=PROJECT_ID, trace_detail=detail)
        assert isinstance(result.findings, list)
        assert "Cost analysis is unavailable" in result.limitations[0]

    def test_coverage_counts(self):
        detail = trace_detail(
            [
                span("root", name="root"),
                span(
                    "tool",
                    parent_span_id="root",
                    start_offset_ms=1,
                    attributes={"tool.name": "x"},
                ),
                span(
                    "llm",
                    parent_span_id="root",
                    start_offset_ms=2,
                    attributes={
                        "helios.span.type": "llm",
                        "gen_ai.request.model": "gpt-4o",
                        "gen_ai.usage.input_tokens": 4,
                    },
                ),
                span(
                    "orphan",
                    parent_span_id="missing",
                    start_offset_ms=3,
                    status_code=2,
                ),
            ]
        )
        cov = analyze_trace(project_id=PROJECT_ID, trace_detail=detail).coverage
        assert cov.total_spans == 4
        assert cov.error_spans == 1
        assert cov.tool_like_spans == 1
        assert cov.model_like_spans == 1
        assert cov.spans_with_model_data == 1
        assert cov.spans_with_token_data == 1
        assert cov.orphan_spans == 1
