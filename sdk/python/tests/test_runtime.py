"""Provider lifecycle ownership and manual semantic-span helpers."""

import asyncio

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import StatusCode

from helios_sdk import runtime, semconv
from helios_sdk.errors import HeliosConfigurationError


class _FakeExporter(SpanExporter):
    """No-network span exporter capturing exported spans."""

    def __init__(self, *args, **kwargs):
        self.spans = []

    def export(self, spans):
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=30000):
        return True


@pytest.fixture()
def patched_exporter(monkeypatch):
    holder = {}

    def factory(*args, **kwargs):
        exp = _FakeExporter()
        holder["exporter"] = exp
        return exp

    monkeypatch.setattr(runtime, "OTLPSpanExporter", factory)
    return holder


def _configure(**overrides):
    kwargs = dict(api_key="test-key", service_name="svc", endpoint="http://localhost:8000")
    kwargs.update(overrides)
    return runtime.Helios.configure(**kwargs)


class TestProviderLifecycle:
    def test_no_existing_provider_creates_and_owns(self, patched_exporter):
        helios = _configure()
        assert helios._owns_provider is True
        assert trace.get_tracer_provider() is helios._provider

    def test_attaches_to_existing_sdk_provider(self, patched_exporter):
        preset = TracerProvider()
        trace.set_tracer_provider(preset)
        helios = _configure()
        assert helios._owns_provider is False
        assert helios._provider is preset
        assert trace.get_tracer_provider() is preset  # not replaced

    def test_incompatible_provider_raises(self, patched_exporter, monkeypatch):
        monkeypatch.setattr(runtime.trace, "get_tracer_provider", lambda: object())
        with pytest.raises(HeliosConfigurationError, match="refusing to replace"):
            _configure()

    def test_idempotent_repeated_setup(self, patched_exporter):
        first = _configure()
        second = _configure()
        assert first is second

    def test_conflicting_configuration_raises(self, patched_exporter):
        _configure(service_name="svc-a")
        with pytest.raises(HeliosConfigurationError, match="different settings"):
            _configure(service_name="svc-b")

    def test_reconfigure_after_shutdown(self, patched_exporter):
        first = _configure()
        first.shutdown()
        second = _configure()
        assert second is not first

    def test_force_flush(self, patched_exporter):
        helios = _configure()
        assert helios.force_flush() is True

    def test_shutdown_is_idempotent(self, patched_exporter):
        helios = _configure()
        helios.shutdown()
        helios.shutdown()  # no error
        assert runtime._active is None
        assert helios.force_flush() is False

    def test_no_network_during_configuration(self, patched_exporter, monkeypatch):
        import socket

        def boom(*args, **kwargs):
            raise AssertionError("network access during configuration")

        monkeypatch.setattr(socket.socket, "connect", boom)
        helios = _configure()  # must not connect
        assert helios is not None


class TestManualHelpers:
    def test_parent_child_propagation(self, inmemory_helios):
        helios, exporter = inmemory_helios
        with helios.agent("agent-run"):
            with helios.retrieval("kb.search"):
                pass
        spans = {s.name: s for s in exporter.get_finished_spans()}
        agent_span = spans["agent-run"]
        child = spans["kb.search"]
        assert child.parent is not None
        assert child.parent.span_id == agent_span.context.span_id

    def test_span_type_attributes(self, inmemory_helios):
        helios, exporter = inmemory_helios
        with helios.agent("a"):
            pass
        with helios.retrieval("r"):
            pass
        with helios.tool("t"):
            pass
        with helios.span("c"):
            pass
        types = {
            s.name: s.attributes[semconv.HELIOS_SPAN_TYPE]
            for s in exporter.get_finished_spans()
        }
        assert types == {"a": "agent", "r": "retrieval", "t": "tool", "c": "custom"}

    def test_llm_maps_genai_attributes_when_supplied(self, inmemory_helios):
        helios, exporter = inmemory_helios
        with helios.llm("chat", model="gpt-4o-mini", operation="chat", system="openai"):
            pass
        span = exporter.get_finished_spans()[0]
        assert span.attributes[semconv.GEN_AI_REQUEST_MODEL] == "gpt-4o-mini"
        assert span.attributes[semconv.GEN_AI_OPERATION_NAME] == "chat"
        assert span.attributes[semconv.GEN_AI_SYSTEM] == "openai"

    def test_no_fabricated_genai_fields(self, inmemory_helios):
        helios, exporter = inmemory_helios
        with helios.agent("a"):
            pass
        with helios.llm("chat"):  # nothing supplied
            pass
        for span in exporter.get_finished_spans():
            gen_ai_keys = [k for k in span.attributes if k.startswith("gen_ai.")]
            assert gen_ai_keys == []  # nothing invented
            # no token/cost/prompt/response fabricated
            assert not any("token" in k or "cost" in k or "prompt" in k for k in span.attributes)

    def test_explicit_attributes_and_validation(self, inmemory_helios):
        helios, exporter = inmemory_helios
        with helios.tool("t", count=3, ok=True, ratio=0.5, tags=["a", "b"], obj={"x": 1}, skip=None):
            pass
        attrs = exporter.get_finished_spans()[0].attributes
        assert attrs["count"] == 3
        assert attrs["ok"] is True
        assert attrs["ratio"] == 0.5
        assert list(attrs["tags"]) == ["a", "b"]
        assert attrs["obj"] == "{'x': 1}"  # unsupported type stringified
        assert "skip" not in attrs  # None dropped

    def test_sync_decorator_preserves_metadata_and_returns(self, inmemory_helios):
        helios, exporter = inmemory_helios

        @helios.trace("do-work")
        def work(x, y):
            "docstring"
            return x + y

        assert work(2, 3) == 5
        assert work.__name__ == "work"
        assert work.__doc__ == "docstring"
        assert exporter.get_finished_spans()[0].name == "do-work"

    def test_async_decorator(self, inmemory_helios):
        helios, exporter = inmemory_helios

        @helios.trace()
        async def fetch(x):
            return x * 2

        result = asyncio.run(fetch(21))
        assert result == 42
        span = exporter.get_finished_spans()[0]
        assert span.name.endswith("fetch")

    def test_exception_recorded_and_reraised(self, inmemory_helios):
        helios, exporter = inmemory_helios

        class Boom(RuntimeError):
            pass

        with pytest.raises(Boom):
            with helios.agent("a"):
                raise Boom("kaboom")

        span = exporter.get_finished_spans()[0]
        assert span.status.status_code == StatusCode.ERROR
        assert any(e.name == "exception" for e in span.events)

    def test_async_decorator_records_exception(self, inmemory_helios):
        helios, exporter = inmemory_helios

        @helios.trace("boom")
        async def fail():
            raise ValueError("bad")

        with pytest.raises(ValueError):
            asyncio.run(fail())
        assert exporter.get_finished_spans()[0].status.status_code == StatusCode.ERROR

    def test_content_not_captured_by_default(self, inmemory_helios):
        helios, exporter = inmemory_helios
        with helios.agent("a"):
            pass
        attrs = exporter.get_finished_spans()[0].attributes
        # Only the helios span-type marker; no content auto-captured.
        assert set(attrs.keys()) == {semconv.HELIOS_SPAN_TYPE}

    def test_repr_does_not_expose_api_key(self, inmemory_helios):
        helios, _ = inmemory_helios
        assert "test-key" not in repr(helios)

    def test_raw_tracer_access(self, inmemory_helios):
        helios, _ = inmemory_helios
        assert helios.tracer is not None
