"""Tests for GET /v1/traces and GET /v1/traces/{trace_id}.

Legacy /v1 routes are mounted only under explicit demo mode, so this module
overrides `client` to use the demo-enabled app (see conftest.legacy_demo_client).
"""

from datetime import datetime

import pytest

from helpers import make_trace_payload


@pytest.fixture()
def client(legacy_demo_client):
    return legacy_demo_client


def test_list_returns_ingested_trace(client):
    payload = make_trace_payload(trace_id="trc_list0001")
    client.post("/v1/traces", json=payload)

    response = client.get("/v1/traces")

    assert response.status_code == 200
    trace_ids = [trace["trace_id"] for trace in response.json()]
    assert "trc_list0001" in trace_ids


def test_list_filters_by_project_slug(client):
    client.post("/v1/traces", json=make_trace_payload(
        trace_id="trc_alpha001", project_slug="project-alpha-test"))
    client.post("/v1/traces", json=make_trace_payload(
        trace_id="trc_beta0001", project_slug="project-beta-test"))

    response = client.get("/v1/traces", params={"project_slug": "project-alpha-test"})

    rows = response.json()
    assert [trace["trace_id"] for trace in rows] == ["trc_alpha001"]
    assert rows[0]["project_slug"] == "project-alpha-test"


def test_detail_returns_trace_with_spans(client):
    payload = make_trace_payload(trace_id="trc_detail01")
    client.post("/v1/traces", json=payload)

    response = client.get("/v1/traces/trc_detail01")

    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"] == "trc_detail01"
    assert len(body["spans"]) == 4
    # Spans are returned sorted by started_at.
    started = [datetime.fromisoformat(span["started_at"]) for span in body["spans"]]
    assert started == sorted(started)


def test_missing_trace_returns_404(client):
    response = client.get("/v1/traces/trc_does_not_exist")

    assert response.status_code == 404
    assert "trc_does_not_exist" in response.json()["detail"]
