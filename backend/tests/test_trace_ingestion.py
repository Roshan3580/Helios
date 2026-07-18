"""Tests for POST /v1/traces — the v1 ingestion contract."""

from app.models import Project, Span, Trace

from helpers import make_trace_payload


def test_ingest_valid_trace_returns_201_with_detail(client):
    payload = make_trace_payload()

    response = client.post("/v1/traces", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["trace_id"] == payload["trace_id"]
    assert body["project_slug"] == payload["project_slug"]
    assert len(body["spans"]) == len(payload["spans"])


def test_ingest_persists_project_trace_and_spans(client, db_session):
    payload = make_trace_payload()

    assert client.post("/v1/traces", json=payload).status_code == 201

    project = db_session.query(Project).filter_by(slug=payload["project_slug"]).one()
    assert project.name == payload["project_name"]
    assert project.environment == payload["environment"]

    trace = db_session.query(Trace).filter_by(trace_id=payload["trace_id"]).one()
    assert trace.project_id == project.id
    assert trace.user_query == payload["user_query"]
    assert trace.total_tokens == payload["total_tokens"]

    spans = db_session.query(Span).filter_by(trace_id=trace.id).all()
    assert {span.span_id for span in spans} == {s["span_id"] for s in payload["spans"]}


def test_nested_parent_span_ids_survive_persistence(client):
    payload = make_trace_payload(trace_id="trc_nested01")

    client.post("/v1/traces", json=payload)
    detail = client.get(f"/v1/traces/{payload['trace_id']}").json()

    parents = {span["span_id"]: span["parent_span_id"] for span in detail["spans"]}
    assert parents["trc_nested01_input"] is None
    assert parents["trc_nested01_rag"] == "trc_nested01_input"
    assert parents["trc_nested01_llm"] == "trc_nested01_input"
    # Depth-2 nesting: tool span parented to the llm span, not the root.
    assert parents["trc_nested01_tool"] == "trc_nested01_llm"


def test_ingest_response_shape_matches_submission(client):
    payload = make_trace_payload(trace_id="trc_shape001")

    body = client.post("/v1/traces", json=payload).json()

    for field in (
        "user_query",
        "app_name",
        "model",
        "status",
        "latency_ms",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
        "estimated_cost_usd",
    ):
        assert body[field] == payload[field], field

    llm_span = next(s for s in body["spans"] if s["span_type"] == "llm")
    assert llm_span["provider"] == "openai"
    assert llm_span["token_count"] == 1500
    assert llm_span["cost_usd"] == 0.0042
    assert llm_span["output_preview"] == "Create a new key, migrate, revoke."

    rag_span = next(s for s in body["spans"] if s["span_type"] == "rag")
    assert rag_span["metadata_json"] == {"top_k": 3}


def test_ingest_rejects_negative_latency(client):
    payload = make_trace_payload(latency_ms=-1)

    response = client.post("/v1/traces", json=payload)

    assert response.status_code == 422


def test_duplicate_trace_id_returns_400_v1_characterization(client):
    """V1 CHARACTERIZATION — documents current behavior, not desired behavior.

    Re-submitting the same trace_id currently violates the unique index on
    traces.trace_id and surfaces as a generic 400 whose detail leaks the
    database error text. A future batch should replace this with explicit
    duplicate handling (e.g. 409 or idempotent accept). Do not "fix" this
    here; update this test intentionally when that redesign lands.
    """
    payload = make_trace_payload(trace_id="trc_dup00001")

    first = client.post("/v1/traces", json=payload)
    assert first.status_code == 201

    second = client.post("/v1/traces", json=payload)
    assert second.status_code == 400
    # The 400 detail is the raw exception string (known v1 flaw).
    detail = second.json()["detail"]
    assert isinstance(detail, str) and detail
