"""Isolation fixtures for v2 SDK tests.

Global OpenTelemetry state (the process-wide tracer provider and OpenAI
instrumentation) is reset around every test so provider-lifecycle behavior can
be exercised deterministically without cross-test leakage.
"""

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from helios_sdk import runtime
from helios_sdk.config import resolve_config


@pytest.fixture(autouse=True)
def reset_global_otel():
    """Reset the Helios runtime, global provider, and OpenAI instrumentation."""
    runtime._reset_for_tests()
    _uninstrument_openai()
    yield
    runtime._reset_for_tests()
    _uninstrument_openai()


def _uninstrument_openai():
    try:
        from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

        inst = OpenAIInstrumentor()
        if inst.is_instrumented_by_opentelemetry:
            inst.uninstrument()
    except Exception:
        pass


CHAT_COMPLETION_RESPONSE = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 1,
    "model": "gpt-4o-mini",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "deterministic answer"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
}

SECRET_PROMPT = "SECRET-PROMPT-CONTENT-should-not-leak"


def make_openai_client(*, error: bool = False):
    """A real openai.OpenAI client wired to a mock transport (no network)."""
    import httpx
    from openai import OpenAI

    def handler(request):
        if error:
            return httpx.Response(500, json={"error": {"message": "boom", "type": "server_error"}})
        return httpx.Response(200, json=CHAT_COMPLETION_RESPONSE)

    return OpenAI(
        api_key="sk-test-not-real",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def make_async_openai_client():
    import httpx
    from openai import AsyncOpenAI

    def handler(request):
        return httpx.Response(200, json=CHAT_COMPLETION_RESPONSE)

    return AsyncOpenAI(
        api_key="sk-test-not-real",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


@pytest.fixture()
def inmemory_helios():
    """A Helios bound to an in-memory exporter (no network, no global provider).

    Returns (helios, exporter). Exercises the real helper/instrumentation code
    while capturing spans in memory.
    """
    config = resolve_config(api_key="test-key", service_name="unit-svc", environment="test")
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    processor = SimpleSpanProcessor(exporter)
    provider.add_span_processor(processor)
    helios = runtime.Helios(config, provider, processor, owns_provider=True)
    return helios, exporter
