"""Tests for the canonical v2 read APIs (/v2/traces) and schema/migration checks."""

from datetime import datetime

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from opentelemetry.proto.trace.v1.trace_pb2 import Status

from otlp_helpers import (
    SPAN_ID_ROOT,
    TRACE_ID_A,
    TRACE_ID_B,
    make_request,
    make_span,
    nested_trace_spans,
    post_otlp,
)


class TestMigrationAndSchema:
    def test_migration_head_creates_otel_tables(self, db_session):
        inspector = inspect(db_session.get_bind())
        tables = inspector.get_table_names()
        assert "otel_traces" in tables
        assert "otel_spans" in tables
        # Legacy tables untouched and present.
        assert "traces" in tables
        assert "spans" in tables

    def test_alembic_version_is_new_head(self, db_session):
        version = db_session.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "002_otel_foundation"

    def test_span_identity_unique_within_project_trace(self, client, db_session):
        post_otlp(client, make_request([make_span()]))
        # Direct duplicate insert violates the composite unique constraint.
        with pytest.raises(IntegrityError):
            db_session.execute(
                text(
                    """
                    INSERT INTO otel_spans (
                        id, project_id, otel_trace_id, trace_id, span_id, name, kind,
                        start_time, end_time, duration_ns, status_code,
                        resource_attributes, scope_attributes, attributes, events, links,
                        dropped_attributes_count, dropped_events_count, dropped_links_count,
                        created_at, updated_at
                    )
                    SELECT gen_random_uuid(), project_id, otel_trace_id, trace_id, span_id,
                           'dup', 0, start_time, end_time, duration_ns, 0,
                           '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, '[]'::jsonb,
                           0, 0, 0, now(), now()
                    FROM otel_spans LIMIT 1
                    """
                )
            )
        db_session.rollback()

    def test_legacy_tables_remain_usable(self, client):
        """Legacy /v1 ingestion still works with the new migration applied."""
        from helpers import make_trace_payload

        response = client.post("/v1/traces", json=make_trace_payload())
        assert response.status_code == 201


class TestV2TraceList:
    def test_project_slug_is_required(self, client):
        response = client.get("/v2/traces")
        assert response.status_code == 422  # missing required query param

    def test_list_returns_only_requested_project(self, client):
        post_otlp(client, make_request(nested_trace_spans()), project_slug="proj-a")
        post_otlp(
            client,
            make_request([make_span(trace_id=TRACE_ID_B)]),
            project_slug="proj-b",
        )

        rows = client.get("/v2/traces", params={"project_slug": "proj-a"}).json()

        assert len(rows) == 1
        assert rows[0]["trace_id"] == TRACE_ID_A.hex()
        assert rows[0]["project_slug"] == "proj-a"

    def test_summary_fields_are_canonical(self, client):
        post_otlp(client, make_request(nested_trace_spans()))

        row = client.get("/v2/traces", params={"project_slug": "otel-proj"}).json()[0]

        assert row["service_name"] == "test-service"
        assert row["span_count"] == 3
        assert row["error_count"] == 1
        assert row["root_span_name"] == "agent.run"
        assert row["duration_ms"] == pytest.approx(50.0)
        # No fabricated GenAI fields in the v2 model.
        for forbidden in ("user_query", "model", "total_tokens", "estimated_cost_usd"):
            assert forbidden not in row

    def test_service_name_filter(self, client):
        post_otlp(client, make_request([make_span()], service_name="svc-a"))
        post_otlp(
            client,
            make_request([make_span(trace_id=TRACE_ID_B)], service_name="svc-b"),
        )

        rows = client.get(
            "/v2/traces", params={"project_slug": "otel-proj", "service_name": "svc-b"}
        ).json()

        assert [r["service_name"] for r in rows] == ["svc-b"]

    def test_has_errors_filter(self, client):
        post_otlp(client, make_request(nested_trace_spans()))  # has an error span
        post_otlp(
            client,
            make_request(
                [make_span(trace_id=TRACE_ID_B, status_code=Status.STATUS_CODE_OK)]
            ),
        )

        errored = client.get(
            "/v2/traces", params={"project_slug": "otel-proj", "has_errors": "true"}
        ).json()
        clean = client.get(
            "/v2/traces", params={"project_slug": "otel-proj", "has_errors": "false"}
        ).json()

        assert [r["trace_id"] for r in errored] == [TRACE_ID_A.hex()]
        assert [r["trace_id"] for r in clean] == [TRACE_ID_B.hex()]

    def test_unknown_project_returns_empty_list(self, client):
        rows = client.get("/v2/traces", params={"project_slug": "nope"}).json()
        assert rows == []


class TestV2TraceDetail:
    def test_detail_returns_timeline_sorted_spans(self, client):
        post_otlp(client, make_request(nested_trace_spans()))

        detail = client.get(
            f"/v2/traces/{TRACE_ID_A.hex()}", params={"project_slug": "otel-proj"}
        ).json()

        assert detail["trace_id"] == TRACE_ID_A.hex()
        assert [s["name"] for s in detail["spans"]] == [
            "agent.run",
            "retriever.search",
            "tool.lookup",
        ]
        starts = [datetime.fromisoformat(s["start_time"]) for s in detail["spans"]]
        assert starts == sorted(starts)
        root = detail["spans"][0]
        assert root["parent_span_id"] is None
        assert root["span_id"] == SPAN_ID_ROOT.hex()
        assert root["kind"] == 2  # SPAN_KIND_SERVER
        error_span = detail["spans"][2]
        assert error_span["status_code"] == 2
        assert error_span["status_message"] == "tool timeout"
        assert error_span["resource_attributes"]["service.name"] == "test-service"
        assert error_span["scope_name"] == "helios.tests"
        assert error_span["duration_ms"] == pytest.approx(3.0)

    def test_cross_project_lookup_returns_404(self, client):
        post_otlp(client, make_request([make_span()]), project_slug="proj-a")
        # proj-b exists but does not own this trace.
        post_otlp(
            client,
            make_request([make_span(trace_id=TRACE_ID_B)]),
            project_slug="proj-b",
        )

        response = client.get(
            f"/v2/traces/{TRACE_ID_A.hex()}", params={"project_slug": "proj-b"}
        )
        assert response.status_code == 404

    def test_missing_trace_returns_404(self, client):
        post_otlp(client, make_request([make_span()]))
        response = client.get(
            "/v2/traces/ffffffffffffffffffffffffffffffff",
            params={"project_slug": "otel-proj"},
        )
        assert response.status_code == 404

    def test_detail_requires_project_slug(self, client):
        response = client.get(f"/v2/traces/{TRACE_ID_A.hex()}")
        assert response.status_code == 422
