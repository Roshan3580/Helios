"""Tests for POST /v1/otlp/traces request handling and persistence."""

import pytest
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
    make_request,
    make_span,
    nested_trace_spans,
    post_otlp,
)


class TestRequestHandling:
    def test_valid_export_returns_200_with_protobuf_response(self, client):
        response = post_otlp(client, make_request(nested_trace_spans()))

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/x-protobuf")
        # Body must decode as an official ExportTraceServiceResponse.
        decoded = ExportTraceServiceResponse()
        decoded.ParseFromString(response.content)
        assert not decoded.HasField("partial_success")

    def test_missing_project_header_is_rejected(self, client):
        request = make_request([make_span()])
        response = client.post(
            "/v1/otlp/traces",
            content=request.SerializeToString(),
            headers=PROTOBUF_HEADERS,
        )
        assert response.status_code == 400
        assert "X-Helios-Project-Slug" in response.json()["detail"]

    def test_blank_project_slug_is_rejected(self, client):
        response = post_otlp(client, make_request([make_span()]), project_slug="   ")
        assert response.status_code == 400

    def test_unsupported_content_type_returns_415(self, client):
        request = make_request([make_span()])
        response = client.post(
            "/v1/otlp/traces",
            content=request.SerializeToString(),
            headers={
                "Content-Type": "application/json",
                "X-Helios-Project-Slug": "otel-proj",
            },
        )
        assert response.status_code == 415

    def test_empty_body_is_rejected(self, client):
        response = client.post(
            "/v1/otlp/traces",
            content=b"",
            headers={**PROTOBUF_HEADERS, "X-Helios-Project-Slug": "otel-proj"},
        )
        assert response.status_code == 400
        assert "empty" in response.json()["detail"]

    def test_oversized_body_returns_413(self, client, monkeypatch):
        from app.routers import otlp as otlp_router

        monkeypatch.setattr(otlp_router, "MAX_REQUEST_BODY_BYTES", 64)
        response = post_otlp(client, make_request(nested_trace_spans()))
        assert response.status_code == 413

    def test_malformed_protobuf_returns_400_without_internals(self, client):
        response = client.post(
            "/v1/otlp/traces",
            content=b"\xff\xfe\xfd garbage",
            headers={**PROTOBUF_HEADERS, "X-Helios-Project-Slug": "otel-proj"},
        )
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "malformed" in detail
        assert "Traceback" not in detail

    def test_multiple_resource_and_scope_groups_in_one_request(self, client):
        request = make_request([make_span()], service_name="svc-a")
        # Second resource group with its own scope and a different trace.
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

        response = post_otlp(client, request)
        assert response.status_code == 200

        traces = client.get(
            "/v2/traces", params={"project_slug": "otel-proj"}
        ).json()
        assert {t["trace_id"] for t in traces} == {TRACE_ID_A.hex(), TRACE_ID_B.hex()}
        by_id = {t["trace_id"]: t for t in traces}
        assert by_id[TRACE_ID_A.hex()]["service_name"] == "svc-a"
        assert by_id[TRACE_ID_B.hex()]["service_name"] == "unknown_service"

    def test_multiple_traces_in_one_scope(self, client):
        request = make_request(
            [
                make_span(trace_id=TRACE_ID_A, span_id=SPAN_ID_ROOT),
                make_span(trace_id=TRACE_ID_B, span_id=SPAN_ID_ROOT, name="second"),
            ]
        )
        response = post_otlp(client, request)
        assert response.status_code == 200

        traces = client.get("/v2/traces", params={"project_slug": "otel-proj"}).json()
        assert len(traces) == 2


class TestPersistence:
    def test_trace_spans_and_project_scoping_persist(self, client, db_session):
        post_otlp(client, make_request(nested_trace_spans()), project_slug="otel-proj")

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

    def test_environment_header_used_as_fallback(self, client, db_session):
        post_otlp(
            client,
            make_request([make_span()]),
            extra_headers={"X-Helios-Environment": "staging"},
        )
        trace = db_session.query(OtelTrace).one()
        assert trace.environment == "staging"

    def test_identical_replay_is_idempotent(self, client, db_session):
        request = make_request(nested_trace_spans())
        assert post_otlp(client, request).status_code == 200
        assert post_otlp(client, request).status_code == 200

        assert db_session.query(OtelTrace).count() == 1
        assert db_session.query(OtelSpan).count() == 3
        trace = db_session.query(OtelTrace).one()
        assert trace.span_count == 3
        assert trace.error_count == 1

    def test_incremental_batch_extends_existing_trace(self, client, db_session):
        spans = nested_trace_spans()
        # Batch 1: child + grandchild only (no root yet).
        post_otlp(client, make_request(spans[1:]))
        trace = db_session.query(OtelTrace).one()
        assert trace.span_count == 2
        assert trace.root_span_id is None

        # Batch 2: the root span arrives later.
        post_otlp(client, make_request(spans[:1]))
        db_session.expire_all()
        trace = db_session.query(OtelTrace).one()
        assert trace.span_count == 3
        assert trace.error_count == 1
        assert trace.root_span_id == SPAN_ID_ROOT.hex()
        assert trace.root_span_name == "agent.run"
        # Summary start/end recomputed across both batches.
        spans_db = db_session.query(OtelSpan).all()
        assert trace.start_time == min(s.start_time for s in spans_db)
        assert trace.end_time == max(s.end_time for s in spans_db)

    def test_resent_span_with_changed_content_overwrites(self, client, db_session):
        post_otlp(client, make_request([make_span(name="original")]))
        post_otlp(client, make_request([make_span(name="rewritten")]))

        assert db_session.query(OtelSpan).count() == 1
        assert db_session.query(OtelSpan).one().name == "rewritten"
        assert db_session.query(OtelTrace).one().span_count == 1

    def test_same_trace_id_isolated_between_projects(self, client, db_session):
        request = make_request([make_span()])
        post_otlp(client, request, project_slug="project-one")
        post_otlp(client, request, project_slug="project-two")

        traces = db_session.query(OtelTrace).all()
        assert len(traces) == 2
        assert len({t.project_id for t in traces}) == 2

    def test_invalid_batch_rolls_back_entirely(self, client, db_session):
        request = make_request(
            [make_span(), make_span(span_id=b"\x00" * 8, name="bad")]
        )
        response = post_otlp(client, request)

        assert response.status_code == 400
        assert db_session.query(OtelTrace).count() == 0
        assert db_session.query(OtelSpan).count() == 0

    def test_attributes_events_links_round_trip(self, client, db_session):
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
        post_otlp(client, request)

        span = db_session.query(OtelSpan).one()
        assert span.attributes == {"gen_ai.system": "openai"}
        assert span.events[0]["name"] == "retrieval.chunk"
        assert span.events[0]["attributes"] == {"chunk.id": "docs/security.md"}
        assert span.links[0]["trace_id"] == TRACE_ID_B.hex()
        assert span.links[0]["span_id"] == SPAN_ID_CHILD.hex()
