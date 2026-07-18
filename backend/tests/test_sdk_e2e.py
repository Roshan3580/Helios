"""End-to-end: the v2 Python SDK exporting through authenticated OTLP to the
real FastAPI backend over a real socket, into the isolated Postgres test DB.

Runs a live uvicorn server in-process (the TestClient can't receive the SDK's
real OTLPSpanExporter HTTP POSTs). Skipped if the SDK's OTel runtime or OpenAI
extra is not installed.
"""

import socket
import threading
import time

import httpx
import pytest

pytest.importorskip("opentelemetry.sdk")
pytest.importorskip("opentelemetry.instrumentation.openai_v2")
helios_runtime = pytest.importorskip("helios_sdk.runtime")

from app.models_otel import OtelSpan, OtelTrace  # noqa: E402
from app.services import api_key_service  # noqa: E402

SECRET_PROMPT = "E2E-SECRET-PROMPT-do-not-store"
CHAT_RESPONSE = {
    "id": "chatcmpl-e2e",
    "object": "chat.completion",
    "created": 1,
    "model": "gpt-4o-mini",
    "choices": [
        {"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
    ],
    "usage": {"prompt_tokens": 9, "completion_tokens": 2, "total_tokens": 11},
}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def live_server():
    import uvicorn

    from app.main import app

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError("uvicorn did not start")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture(autouse=True)
def reset_helios():
    helios_runtime._reset_for_tests()
    _uninstrument()
    yield
    helios_runtime._reset_for_tests()
    _uninstrument()


def _uninstrument():
    try:
        from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

        inst = OpenAIInstrumentor()
        if inst.is_instrumented_by_opentelemetry:
            inst.uninstrument()
    except Exception:
        pass


def _mock_openai_client():
    from openai import OpenAI

    return OpenAI(
        api_key="sk-e2e-not-real",
        http_client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=CHAT_RESPONSE))),
    )


def _make_keys(db_session):
    project = api_key_service.get_or_create_project(
        db_session, slug="e2e-proj", name="E2E", environment="e2e-test"
    )
    ingest = api_key_service.create_api_key(
        db_session, project=project, name="ingest", scopes=["traces:ingest"]
    )
    read = api_key_service.create_api_key(
        db_session, project=project, name="read", scopes=["traces:read"]
    )
    db_session.commit()
    return ingest.token, read.token


def test_sdk_exports_through_authenticated_otlp(live_server, db_session):
    ingest_token, read_token = _make_keys(db_session)

    helios = helios_runtime.Helios.configure(
        api_key=ingest_token,
        service_name="e2e-support-agent",
        endpoint=live_server,
        environment="e2e-test",
    )
    helios.instrument_openai()  # content off by default

    with helios.agent("support-agent") as agent_span:
        trace_id = format(agent_span.get_span_context().trace_id, "032x")
        with helios.retrieval("kb.search") as r:
            r.set_attribute("retrieval.top_k", 3)
        _mock_openai_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": SECRET_PROMPT}],
        )

    assert helios.force_flush() is True
    helios.shutdown()

    # --- persistence in the canonical v2 store ---
    trace = db_session.query(OtelTrace).filter_by(trace_id=trace_id).one()
    assert trace.service_name == "e2e-support-agent"
    assert trace.environment == "e2e-test"
    assert trace.span_count == 3
    spans = {s.name: s for s in db_session.query(OtelSpan).filter_by(otel_trace_id=trace.id)}
    assert "support-agent" in spans
    assert "kb.search" in spans
    openai_span = next(s for s in spans.values() if s.attributes.get("gen_ai.operation.name"))
    # parent-child: retrieval + openai spans are children of the agent root.
    root = spans["support-agent"]
    assert spans["kb.search"].parent_span_id == root.span_id
    assert openai_span.parent_span_id == root.span_id
    # semantic attributes from the instrumentor.
    assert openai_span.attributes["gen_ai.request.model"] == "gpt-4o-mini"
    assert openai_span.attributes["gen_ai.usage.input_tokens"] == 9
    # no prompt content by default anywhere in the trace.
    import json as _json

    blob = _json.dumps([
        {"attrs": s.attributes, "events": s.events} for s in spans.values()
    ])
    assert SECRET_PROMPT not in blob

    # --- read via /v2/traces with a read-scoped key over the live server ---
    read_headers = {"Authorization": f"Bearer {read_token}"}
    listing = httpx.get(f"{live_server}/v2/traces", headers=read_headers).json()
    assert any(t["trace_id"] == trace_id for t in listing)
    detail = httpx.get(f"{live_server}/v2/traces/{trace_id}", headers=read_headers).json()
    assert detail["service_name"] == "e2e-support-agent"
    assert {s["name"] for s in detail["spans"]} >= {"support-agent", "kb.search"}

    # --- ingest-only key cannot read ---
    denied = httpx.get(
        f"{live_server}/v2/traces", headers={"Authorization": f"Bearer {ingest_token}"}
    )
    assert denied.status_code == 403
