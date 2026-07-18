"""Tests for the canonical v2 read APIs (/v2/traces) and schema/migration checks.

Reads authenticate with a project API key (scope traces:read); the project is
derived from the key, so there is no project_slug query parameter.
"""

from datetime import datetime

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from opentelemetry.proto.trace.v1.trace_pb2 import Status

from otlp_helpers import (
    SPAN_ID_ROOT,
    TRACE_ID_A,
    TRACE_ID_B,
    bearer,
    make_request,
    make_span,
    nested_trace_spans,
    post_otlp,
)


class TestMigrationAndSchema:
    def test_migration_head_creates_expected_tables(self, db_session):
        inspector = inspect(db_session.get_bind())
        tables = inspector.get_table_names()
        assert "otel_traces" in tables
        assert "otel_spans" in tables
        assert "project_api_keys" in tables
        # Legacy tables untouched and present.
        assert "traces" in tables
        assert "spans" in tables

    def test_alembic_version_is_new_head(self, db_session):
        version = db_session.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "004_human_identity"

    def test_span_identity_unique_within_project_trace(self, client, db_session, ingest_token):
        post_otlp(client, make_request([make_span()]), token=ingest_token)
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
        """Legacy /v1 ingestion still works with the new migrations applied."""
        from helpers import make_trace_payload

        response = client.post("/v1/traces", json=make_trace_payload())
        assert response.status_code == 201


class TestV2TraceListAuth:
    def test_missing_auth_returns_401(self, client):
        response = client.get("/v2/traces")
        assert response.status_code == 401
        assert response.headers.get("www-authenticate") == "Bearer"

    def test_list_returns_only_authenticated_project(self, client, make_api_key):
        key_a = make_api_key(project_slug="proj-a")
        key_b = make_api_key(project_slug="proj-b")
        post_otlp(client, make_request(nested_trace_spans()), token=key_a.token)
        post_otlp(client, make_request([make_span(trace_id=TRACE_ID_B)]), token=key_b.token)

        rows = client.get("/v2/traces", headers=bearer(key_a.token)).json()

        assert len(rows) == 1
        assert rows[0]["trace_id"] == TRACE_ID_A.hex()
        assert rows[0]["project_slug"] == "proj-a"

    def test_obsolete_project_slug_query_cannot_override(self, client, make_api_key):
        key_a = make_api_key(project_slug="proj-a")
        key_b = make_api_key(project_slug="proj-b")
        post_otlp(client, make_request(nested_trace_spans()), token=key_a.token)
        post_otlp(client, make_request([make_span(trace_id=TRACE_ID_B)]), token=key_b.token)

        # A leftover project_slug param must not change the key-derived scope.
        rows = client.get(
            "/v2/traces",
            params={"project_slug": "proj-b"},
            headers=bearer(key_a.token),
        ).json()

        assert [r["trace_id"] for r in rows] == [TRACE_ID_A.hex()]

    def test_summary_fields_are_canonical(self, client, ingest_token):
        post_otlp(client, make_request(nested_trace_spans()), token=ingest_token)

        row = client.get("/v2/traces", headers=bearer(ingest_token)).json()[0]

        assert row["service_name"] == "test-service"
        assert row["span_count"] == 3
        assert row["error_count"] == 1
        assert row["root_span_name"] == "agent.run"
        assert row["duration_ms"] == pytest.approx(50.0)
        for forbidden in ("user_query", "model", "total_tokens", "estimated_cost_usd"):
            assert forbidden not in row

    def test_service_name_filter(self, client, ingest_token):
        post_otlp(client, make_request([make_span()], service_name="svc-a"), token=ingest_token)
        post_otlp(
            client,
            make_request([make_span(trace_id=TRACE_ID_B)], service_name="svc-b"),
            token=ingest_token,
        )

        rows = client.get(
            "/v2/traces", params={"service_name": "svc-b"}, headers=bearer(ingest_token)
        ).json()

        assert [r["service_name"] for r in rows] == ["svc-b"]

    def test_has_errors_filter(self, client, ingest_token):
        post_otlp(client, make_request(nested_trace_spans()), token=ingest_token)
        post_otlp(
            client,
            make_request(
                [make_span(trace_id=TRACE_ID_B, status_code=Status.STATUS_CODE_OK)]
            ),
            token=ingest_token,
        )

        errored = client.get(
            "/v2/traces", params={"has_errors": "true"}, headers=bearer(ingest_token)
        ).json()
        clean = client.get(
            "/v2/traces", params={"has_errors": "false"}, headers=bearer(ingest_token)
        ).json()

        assert [r["trace_id"] for r in errored] == [TRACE_ID_A.hex()]
        assert [r["trace_id"] for r in clean] == [TRACE_ID_B.hex()]


class TestV2TraceDetail:
    def test_detail_returns_timeline_sorted_spans(self, client, ingest_token):
        post_otlp(client, make_request(nested_trace_spans()), token=ingest_token)

        detail = client.get(
            f"/v2/traces/{TRACE_ID_A.hex()}", headers=bearer(ingest_token)
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

    def test_cross_project_lookup_returns_404(self, client, make_api_key):
        key_a = make_api_key(project_slug="proj-a")
        key_b = make_api_key(project_slug="proj-b")
        post_otlp(client, make_request([make_span()]), token=key_a.token)
        post_otlp(client, make_request([make_span(trace_id=TRACE_ID_B)]), token=key_b.token)

        # proj-b's key cannot retrieve proj-a's trace detail.
        response = client.get(
            f"/v2/traces/{TRACE_ID_A.hex()}", headers=bearer(key_b.token)
        )
        assert response.status_code == 404

    def test_missing_trace_returns_404(self, client, ingest_token):
        post_otlp(client, make_request([make_span()]), token=ingest_token)
        response = client.get(
            "/v2/traces/ffffffffffffffffffffffffffffffff", headers=bearer(ingest_token)
        )
        assert response.status_code == 404

    def test_detail_requires_auth(self, client):
        response = client.get(f"/v2/traces/{TRACE_ID_A.hex()}")
        assert response.status_code == 401
