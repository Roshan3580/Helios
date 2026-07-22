"""Unit tests for TraceBuilder/SpanRecorder — no network involved.

Tests marked "V1 CHARACTERIZATION" pin current v1 behavior (including known
flaws) so regressions are visible; they are expected to be replaced
intentionally during the v2 SDK redesign, not treated as desired behavior.
"""

from datetime import datetime

import pytest

from helios_sdk import HeliosClient


def make_client(**overrides) -> HeliosClient:
    kwargs = {
        "base_url": "http://localhost:9",  # never contacted in these tests
        "project_slug": "sdk-tests",
        "project_name": "SDK Tests",
        "environment": "test",
    }
    kwargs.update(overrides)
    return HeliosClient(**kwargs)


def make_trace(client=None, **overrides):
    client = client or make_client()
    kwargs = {
        "user_query": "How do I test the SDK?",
        "app_name": "sdk-test-app",
        "model": "gpt-4o-mini",
    }
    kwargs.update(overrides)
    return client.create_trace(**kwargs)


class TestTraceCreation:
    def test_generates_prefixed_trace_id(self):
        trace = make_trace()
        assert trace.trace_id.startswith("trc_")

    def test_honors_explicit_trace_id(self):
        trace = make_trace(trace_id="trc_fixed001")
        assert trace.trace_id == "trc_fixed001"
        assert trace.root_span_id == "trc_fixed001_input"

    def test_invalid_trace_status_raises(self):
        with pytest.raises(ValueError):
            make_trace(status="exploded")


class TestSpanRecording:
    def test_context_manager_records_and_finishes_span(self):
        trace = make_trace()

        with trace.span("retriever.search", span_type="rag") as span:
            span.set_input("query text")
            span.set_output("3 chunks")
            span.set_metadata({"top_k": 3})

        assert trace.span_count == 1
        recorded = trace._spans[0]
        assert recorded.name == "retriever.search"
        assert recorded.ended_at is not None
        assert recorded.input_preview == "query text"
        assert recorded.metadata == {"top_k": 3}

    def test_default_parent_is_root_span_id(self):
        trace = make_trace(trace_id="trc_parent01")

        with trace.span("llm.generate", span_type="llm"):
            pass

        assert trace._spans[0].parent_span_id == "trc_parent01_input"

    def test_explicit_parent_span_id_preserved(self):
        trace = make_trace()

        with trace.span("llm.generate", span_type="llm") as llm_span:
            pass
        with trace.span("tool.lookup", span_type="tool", parent_span_id=llm_span.span_id):
            pass

        assert trace._spans[1].parent_span_id == llm_span.span_id

    def test_invalid_span_type_raises(self):
        trace = make_trace()
        with pytest.raises(ValueError):
            with trace.span("bad", span_type="not-a-type"):
                pass

    def test_negative_tokens_rejected(self):
        trace = make_trace()
        with trace.span("llm.generate", span_type="llm") as span:
            with pytest.raises(ValueError):
                span.set_tokens(-1)


class TestPayloadSerialization:
    def test_synthetic_root_span_inserted(self):
        trace = make_trace(trace_id="trc_root0001", user_query="the question")
        with trace.span("llm.generate", span_type="llm"):
            pass

        payload = trace.to_payload(
            project_slug="sdk-tests", project_name="SDK Tests", environment="test"
        )

        root = payload["spans"][0]
        assert root["span_id"] == "trc_root0001_input"
        assert root["name"] == "user.query"
        assert root["span_type"] == "input"
        assert root["parent_span_id"] is None
        assert root["input_preview"] == "the question"
        assert root["metadata_json"] == {"source": "helios_sdk"}

    def test_no_duplicate_root_when_user_query_span_exists(self):
        trace = make_trace()
        with trace.span("user.query", span_type="input"):
            pass

        payload = trace.to_payload(
            project_slug="sdk-tests", project_name="SDK Tests", environment="test"
        )

        assert [s["name"] for s in payload["spans"]].count("user.query") == 1

    def test_payload_shape_and_iso_timestamps(self):
        trace = make_trace()
        with trace.span("llm.generate", span_type="llm", provider="openai",
                        model="gpt-4o-mini") as span:
            span.set_tokens(100)
            span.set_cost(0.001)

        payload = trace.to_payload(
            project_slug="sdk-tests", project_name="SDK Tests", environment="test"
        )

        assert set(payload) == {
            "trace_id", "project_slug", "project_name", "environment",
            "user_query", "app_name", "model", "status", "latency_ms",
            "total_tokens", "prompt_tokens", "completion_tokens",
            "estimated_cost_usd", "spans",
        }
        assert payload["project_slug"] == "sdk-tests"
        assert isinstance(payload["latency_ms"], int)
        assert payload["latency_ms"] >= 0

        llm = payload["spans"][1]
        assert set(llm) == {
            "span_id", "parent_span_id", "name", "span_type", "provider",
            "model", "latency_ms", "token_count", "cost_usd", "status",
            "input_preview", "output_preview", "metadata_json",
            "started_at", "ended_at",
        }
        # Timestamps serialize as parseable ISO-8601 strings.
        datetime.fromisoformat(llm["started_at"])
        datetime.fromisoformat(llm["ended_at"])


class TestAggregationCharacterization:
    def test_llm_tokens_split_75_25_v1_characterization(self):
        """V1 CHARACTERIZATION: prompt/completion tokens are fabricated as a
        75/25 split of llm-span tokens, not measured. Replace in v2."""
        trace = make_trace()
        with trace.span("llm.generate", span_type="llm") as span:
            span.set_tokens(1000)

        payload = trace.to_payload(
            project_slug="sdk-tests", project_name="SDK Tests", environment="test"
        )

        assert payload["total_tokens"] == 1000
        assert payload["prompt_tokens"] == 750
        assert payload["completion_tokens"] == 250

    def test_non_llm_tokens_inflate_total_only_v1_characterization(self):
        """V1 CHARACTERIZATION: tokens on non-llm spans count toward
        total_tokens but not the prompt/completion split, so
        prompt + completion != total. Replace in v2."""
        trace = make_trace()
        with trace.span("retriever.search", span_type="rag") as span:
            span.set_tokens(100)
        with trace.span("llm.generate", span_type="llm") as span:
            span.set_tokens(1000)

        payload = trace.to_payload(
            project_slug="sdk-tests", project_name="SDK Tests", environment="test"
        )

        assert payload["total_tokens"] == 1100
        assert payload["prompt_tokens"] + payload["completion_tokens"] == 1000

    def test_costs_summed_across_spans(self):
        trace = make_trace()
        with trace.span("llm.generate", span_type="llm") as span:
            span.set_cost(0.0012)
        with trace.span("reranker.score", span_type="rag") as span:
            span.set_cost(0.0003)

        payload = trace.to_payload(
            project_slug="sdk-tests", project_name="SDK Tests", environment="test"
        )

        assert payload["estimated_cost_usd"] == pytest.approx(0.0015)
