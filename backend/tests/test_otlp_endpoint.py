"""Tests for POST /v1/otlp/traces request handling and persistence.

All requests authenticate with a real project API key; the project is derived
from the key, never from a header or query parameter.
"""

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceResponse,
)
from opentelemetry.proto.resource.v1.resource_pb2 import Resource
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans, ScopeSpans

from app.models import Project
from app.models_otel import OtelSpan, OtelTrace

from otlp_helpers import (
    PROTOBUF_HEADERS,
    SPAN_ID_CHILD,
    SPAN_ID_ROOT,
    TRACE_ID_A,
    TRACE_ID_B,
    bearer,
    make_request,
    make_span,
    nested_trace_spans,
    post_otlp,
)


class TestRequestHandling:
    def test_valid_export_returns_200_with_protobuf_response(self, client, ingest_token):
        response = post_otlp(client, make_request(nested_trace_spans()), token=ingest_token)

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/x-protobuf")
        decoded = ExportTraceServiceResponse()
        decoded.ParseFromString(response.content)
        assert not decoded.HasField("partial_success")

    def test_missing_auth_returns_401(self, client):
        response = post_otlp(client, make_request([make_span()]), token=None)
        assert response.status_code == 401
        assert response.headers.get("www-authenticate") == "Bearer"

    def test_unsupported_content_type_returns_415(self, client, ingest_token):
        request = make_request([make_span()])
        response = client.post(
            "/v1/otlp/traces",
            content=request.SerializeToString(),
            headers={"Content-Type": "application/json", **bearer(ingest_token)},
        )
        assert response.status_code == 415

    def test_empty_body_is_rejected(self, client, ingest_token):
        response = client.post(
            "/v1/otlp/traces",
            content=b"",
            headers={**PROTOBUF_HEADERS, **bearer(ingest_token)},
        )
        assert response.status_code == 400
        assert "empty" in response.json()["detail"]

    def test_oversized_body_returns_413(self, client, ingest_token, monkeypatch):
        from app.routers import otlp as otlp_router

        monkeypatch.setattr(otlp_router, "MAX_REQUEST_BODY_BYTES", 64)
        response = post_otlp(client, make_request(nested_trace_spans()), token=ingest_token)
        assert response.status_code == 413

    def test_malformed_protobuf_returns_400_without_internals(self, client, ingest_token):
        response = client.post(
            "/v1/otlp/traces",
            content=b"\xff\xfe\xfd garbage",
            headers={**PROTOBUF_HEADERS, **bearer(ingest_token)},
        )
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "malformed" in detail
        assert "Traceback" not in detail

    def test_multiple_resource_and_scope_groups_in_one_request(self, client, make_api_key):
        created = make_api_key(project_slug="otel-proj")
        request = make_request([make_span()], service_name="svc-a")
        request.resource_spans.append(
            ResourceSpans(
                resource=Resource(),
                scope_spans=[
                    ScopeSpans(
                        spans=[
                            make_span(
                                trace_id=TRACE_ID_B,
                                span_id=SPAN_ID_CHILD,
                                name="other.op",
                            )
                        ]
                    )
                ],
            )
        )

        response = post_otlp(client, request, token=created.token)
        assert response.status_code == 200

        traces = client.get("/v2/traces", headers=bearer(created.token)).json()
        assert {t["trace_id"] for t in traces} == {TRACE_ID_A.hex(), TRACE_ID_B.hex()}
        by_id = {t["trace_id"]: t for t in traces}
        assert by_id[TRACE_ID_A.hex()]["service_name"] == "svc-a"
        assert by_id[TRACE_ID_B.hex()]["service_name"] == "unknown_service"

    def test_multiple_traces_in_one_scope(self, client, make_api_key):
        created = make_api_key()
        request = make_request(
            [
                make_span(trace_id=TRACE_ID_A, span_id=SPAN_ID_ROOT),
                make_span(trace_id=TRACE_ID_B, span_id=SPAN_ID_ROOT, name="second"),
            ]
        )
        response = post_otlp(client, request, token=created.token)
        assert response.status_code == 200

        traces = client.get("/v2/traces", headers=bearer(created.token)).json()
        assert len(traces) == 2


class TestPersistence:
    def test_trace_spans_and_project_scoping_persist(self, client, db_session, ingest_token):
        post_otlp(client, make_request(nested_trace_spans()), token=ingest_token)

        project = db_session.query(Project).filter_by(slug="otel-proj").one()
        trace = db_session.query(OtelTrace).filter_by(project_id=project.id).one()
        assert trace.trace_id == TRACE_ID_A.hex()
        assert trace.service_name == "test-service"
        assert trace.span_count == 3
        assert trace.error_count == 1
        assert trace.root_span_id == SPAN_ID_ROOT.hex()
        assert trace.root_span_name == "agent.run"

        spans = (
            db_session.query(OtelSpan)
            .filter_by(otel_trace_id=trace.id)
            .order_by(OtelSpan.start_time)
            .all()
        )
        assert [s.parent_span_id for s in spans] == [
            None,
            SPAN_ID_ROOT.hex(),
            SPAN_ID_CHILD.hex(),
        ]
        assert all(s.project_id == project.id for s in spans)

    def test_ingestion_does_not_create_projects(self, client, db_session, ingest_token):
        """Only the admin path creates projects; ingest uses the key's project."""
        before = db_session.query(Project).count()
        post_otlp(client, make_request([make_span()]), token=ingest_token)
        db_session.expire_all()
        assert db_session.query(Project).count() == before

    def test_environment_header_used_as_fallback(self, client, db_session, ingest_token):
        post_otlp(
            client,
            make_request([make_span()]),
            token=ingest_token,
            extra_headers={"X-Helios-Environment": "staging"},
        )
        trace = db_session.query(OtelTrace).one()
        assert trace.environment == "staging"

    def test_identical_replay_is_idempotent(self, client, db_session, ingest_token):
        request = make_request(nested_trace_spans())
        assert post_otlp(client, request, token=ingest_token).status_code == 200
        assert post_otlp(client, request, token=ingest_token).status_code == 200

        assert db_session.query(OtelTrace).count() == 1
        assert db_session.query(OtelSpan).count() == 3
        trace = db_session.query(OtelTrace).one()
        assert trace.span_count == 3
        assert trace.error_count == 1

    def test_incremental_batch_extends_existing_trace(self, client, db_session, ingest_token):
        spans = nested_trace_spans()
        post_otlp(client, make_request(spans[1:]), token=ingest_token)
        trace = db_session.query(OtelTrace).one()
        assert trace.span_count == 2
        assert trace.root_span_id is None

        post_otlp(client, make_request(spans[:1]), token=ingest_token)
        db_session.expire_all()
        trace = db_session.query(OtelTrace).one()
        assert trace.span_count == 3
        assert trace.error_count == 1
        assert trace.root_span_id == SPAN_ID_ROOT.hex()
        assert trace.root_span_name == "agent.run"
        spans_db = db_session.query(OtelSpan).all()
        assert trace.start_time == min(s.start_time for s in spans_db)
        assert trace.end_time == max(s.end_time for s in spans_db)

    def test_resent_span_with_changed_content_overwrites(self, client, db_session, ingest_token):
        post_otlp(client, make_request([make_span(name="original")]), token=ingest_token)
        post_otlp(client, make_request([make_span(name="rewritten")]), token=ingest_token)

        assert db_session.query(OtelSpan).count() == 1
        assert db_session.query(OtelSpan).one().name == "rewritten"
        assert db_session.query(OtelTrace).one().span_count == 1

    def test_same_trace_id_isolated_between_projects(self, client, db_session, make_api_key):
        key_a = make_api_key(project_slug="project-one")
        key_b = make_api_key(project_slug="project-two")
        request = make_request([make_span()])
        post_otlp(client, request, token=key_a.token)
        post_otlp(client, request, token=key_b.token)

        traces = db_session.query(OtelTrace).all()
        assert len(traces) == 2
        assert len({t.project_id for t in traces}) == 2

    def test_invalid_batch_rolls_back_entirely(self, client, db_session, ingest_token):
        request = make_request(
            [make_span(), make_span(span_id=b"\x00" * 8, name="bad")]
        )
        response = post_otlp(client, request, token=ingest_token)

        assert response.status_code == 400
        assert db_session.query(OtelTrace).count() == 0
        assert db_session.query(OtelSpan).count() == 0

    def test_attributes_events_links_round_trip(self, client, db_session, ingest_token):
        from otlp_helpers import any_string, kv
        from opentelemetry.proto.trace.v1.trace_pb2 import Span as PbSpan

        event = PbSpan.Event(
            name="retrieval.chunk",
            time_unix_nano=1_767_225_600_500_000_000,
            attributes=[kv("chunk.id", any_string("docs/security.md"))],
        )
        link = PbSpan.Link(trace_id=TRACE_ID_B, span_id=SPAN_ID_CHILD)
        request = make_request(
            [
                make_span(
                    attributes=[kv("gen_ai.system", any_string("openai"))],
                    events=[event],
                    links=[link],
                )
            ]
        )
        post_otlp(client, request, token=ingest_token)

        span = db_session.query(OtelSpan).one()
        assert span.attributes == {"gen_ai.system": "openai"}
        assert span.events[0]["name"] == "retrieval.chunk"
        assert span.events[0]["attributes"] == {"chunk.id": "docs/security.md"}
        assert span.links[0]["trace_id"] == TRACE_ID_B.hex()
        assert span.links[0]["span_id"] == SPAN_ID_CHILD.hex()
