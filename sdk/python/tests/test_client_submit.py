"""Tests for HeliosClient.submit_trace() with HTTP mocked — no real network."""

import httpx
import pytest

from helios_sdk import HeliosAPIError, HeliosClient, HeliosConnectionError


class DummyResponse:
    def __init__(self, status_code=201, body=None, text=""):
        self.status_code = status_code
        self._body = body or {}
        self.text = text
        self.reason_phrase = "Bad Request" if status_code >= 400 else "Created"

    def json(self):
        return self._body


@pytest.fixture()
def client():
    return HeliosClient(
        base_url="http://helios.test:8000/",  # trailing slash intentional
        project_slug="sdk-tests",
        project_name="SDK Tests",
        environment="test",
    )


@pytest.fixture()
def trace(client):
    trace = client.create_trace(
        user_query="q", app_name="sdk-test-app", model="gpt-4o-mini"
    )
    with trace.span("llm.generate", span_type="llm"):
        pass
    return trace


def test_submit_posts_payload_to_v1_traces(client, trace, monkeypatch):
    captured = {}

    def fake_post(url, *, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return DummyResponse(201, body={"trace_id": trace.trace_id})

    monkeypatch.setattr("helios_sdk.client.httpx.post", fake_post)

    result = client.submit_trace(trace)

    # Base URL trailing slash is stripped by the client.
    assert captured["url"] == "http://helios.test:8000/v1/traces"
    assert captured["json"]["trace_id"] == trace.trace_id
    assert captured["json"]["project_slug"] == "sdk-tests"
    assert captured["json"]["environment"] == "test"
    assert result == {"trace_id": trace.trace_id}


def test_submit_raises_api_error_on_4xx(client, trace, monkeypatch):
    monkeypatch.setattr(
        "helios_sdk.client.httpx.post",
        lambda url, *, json, timeout: DummyResponse(400, text="duplicate trace"),
    )

    with pytest.raises(HeliosAPIError) as exc_info:
        client.submit_trace(trace)

    assert exc_info.value.status_code == 400
    assert "duplicate trace" in str(exc_info.value)


def test_submit_raises_connection_error_when_unreachable(client, trace, monkeypatch):
    def fake_post(url, *, json, timeout):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("helios_sdk.client.httpx.post", fake_post)

    with pytest.raises(HeliosConnectionError):
        client.submit_trace(trace)
