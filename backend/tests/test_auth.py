"""Authentication, scope enforcement, and project isolation via the HTTP layer.

Exercises the real dependency against /v1/otlp/traces (ingest) and /v2/traces
(read). Uses the OTLP endpoint's 415-on-non-protobuf behavior to prove that a
request got *past* auth (401 would fire before content-type checks).
"""

import logging
from datetime import datetime, timedelta, timezone

from app.models_auth import ProjectAPIKey

from otlp_helpers import (
    PROTOBUF_HEADERS,
    TRACE_ID_A,
    TRACE_ID_B,
    bearer,
    make_request,
    make_span,
    nested_trace_spans,
    post_otlp,
)

GENERIC_401 = "invalid authentication credentials"


def _read(client, token):
    return client.get("/v2/traces", headers=bearer(token))


class TestAuthenticationCategories:
    def test_missing_header_401(self, client):
        assert _read(client, "").status_code == 401
        resp = client.get("/v2/traces")
        assert resp.status_code == 401
        assert resp.headers.get("www-authenticate") == "Bearer"

    def test_non_bearer_scheme_401(self, client, ingest_token):
        resp = client.get("/v2/traces", headers={"Authorization": f"Basic {ingest_token}"})
        assert resp.status_code == 401

    def test_malformed_token_401(self, client):
        resp = client.get("/v2/traces", headers={"Authorization": "Bearer not-a-helios-key"})
        assert resp.status_code == 401

    def test_unknown_token_401(self, client):
        # Well-formed shape but no such prefix in the DB.
        resp = client.get(
            "/v2/traces",
            headers={"Authorization": "Bearer hel_proj_0011223344556677_deadbeefsecret"},
        )
        assert resp.status_code == 401

    def test_altered_token_with_valid_prefix_401(self, client, make_api_key):
        created = make_api_key(scopes=["traces:read"])
        tampered = created.token[:-3] + "zzz"
        resp = _read(client, tampered)
        assert resp.status_code == 401

    def test_revoked_token_401(self, client, db_session, make_api_key):
        from app.services import api_key_service

        created = make_api_key(scopes=["traces:read"])
        key = db_session.get(ProjectAPIKey, created.api_key.id)
        api_key_service.revoke_api_key(db_session, api_key=key)
        db_session.commit()

        assert _read(client, created.token).status_code == 401

    def test_expired_token_401(self, client, make_api_key):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        created = make_api_key(scopes=["traces:read"], expires_at=past)
        assert _read(client, created.token).status_code == 401

    def test_valid_token_updates_last_used_at(self, client, db_session, make_api_key):
        created = make_api_key(scopes=["traces:read"])
        assert created.api_key.last_used_at is None

        assert _read(client, created.token).status_code == 200

        db_session.expire_all()
        key = db_session.get(ProjectAPIKey, created.api_key.id)
        assert key.last_used_at is not None

    def test_error_responses_do_not_reveal_key_state(self, client, make_api_key):
        # unknown, revoked, expired, malformed all return the same generic detail.
        from app.services import api_key_service

        unknown = client.get(
            "/v2/traces",
            headers={"Authorization": "Bearer hel_proj_0011223344556677_x"},
        ).json()["detail"]

        expired = make_api_key(
            project_slug="exp", scopes=["traces:read"],
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        expired_detail = _read(client, expired.token).json()["detail"]

        revoked = make_api_key(project_slug="rev", scopes=["traces:read"])
        # revoke through a fresh session
        from app.database import SessionLocal

        with SessionLocal() as s:
            key = s.get(ProjectAPIKey, revoked.api_key.id)
            api_key_service.revoke_api_key(s, api_key=key)
            s.commit()
        revoked_detail = _read(client, revoked.token).json()["detail"]

        assert unknown == expired_detail == revoked_detail == GENERIC_401

    def test_token_not_present_in_logs(self, client, make_api_key, caplog):
        created = make_api_key(scopes=["traces:read"])
        with caplog.at_level(logging.DEBUG):
            _read(client, created.token)  # success path
            _read(client, created.token[:-3] + "zzz")  # failure path
        combined = "\n".join(record.getMessage() for record in caplog.records)
        secret = "_".join(created.token.split("_")[3:])
        assert created.token not in combined
        assert secret not in combined


class TestScopeEnforcement:
    def test_ingest_only_key_can_ingest_cannot_read(self, client, make_api_key):
        created = make_api_key(scopes=["traces:ingest"])
        assert post_otlp(client, make_request([make_span()]), token=created.token).status_code == 200
        assert _read(client, created.token).status_code == 403

    def test_read_only_key_can_read_cannot_ingest(self, client, make_api_key):
        created = make_api_key(scopes=["traces:read"])
        assert _read(client, created.token).status_code == 200
        resp = post_otlp(client, make_request([make_span()]), token=created.token)
        assert resp.status_code == 403

    def test_combined_key_can_do_both(self, client, make_api_key):
        created = make_api_key(scopes=["traces:ingest", "traces:read"])
        assert post_otlp(client, make_request([make_span()]), token=created.token).status_code == 200
        assert _read(client, created.token).status_code == 200

    def test_missing_scope_returns_403_not_401(self, client, make_api_key):
        created = make_api_key(scopes=["traces:ingest"])
        resp = _read(client, created.token)
        assert resp.status_code == 403
        assert "scope" in resp.json()["detail"].lower()


class TestProjectIsolation:
    def test_key_cannot_write_to_another_project_via_header(self, client, db_session, make_api_key):
        from app.models import Project
        from app.models_otel import OtelTrace

        key_a = make_api_key(project_slug="proj-a")
        make_api_key(project_slug="proj-b")

        # Attempt to redirect ingestion to proj-b using the obsolete header.
        post_otlp(
            client,
            make_request([make_span()]),
            token=key_a.token,
            extra_headers={"X-Helios-Project-Slug": "proj-b"},
        )

        proj_a = db_session.query(Project).filter_by(slug="proj-a").one()
        proj_b = db_session.query(Project).filter_by(slug="proj-b").one()
        assert db_session.query(OtelTrace).filter_by(project_id=proj_a.id).count() == 1
        assert db_session.query(OtelTrace).filter_by(project_id=proj_b.id).count() == 0

    def test_key_cannot_list_another_project(self, client, make_api_key):
        key_a = make_api_key(project_slug="proj-a")
        key_b = make_api_key(project_slug="proj-b")
        post_otlp(client, make_request([make_span(trace_id=TRACE_ID_B)]), token=key_b.token)

        rows = _read(client, key_a.token).json()
        assert rows == []

    def test_same_trace_id_independent_across_projects(self, client, make_api_key):
        key_a = make_api_key(project_slug="proj-a")
        key_b = make_api_key(project_slug="proj-b")
        post_otlp(client, make_request(nested_trace_spans()), token=key_a.token)
        post_otlp(client, make_request(nested_trace_spans()), token=key_b.token)

        a_detail = client.get(
            f"/v2/traces/{TRACE_ID_A.hex()}", headers=bearer(key_a.token)
        )
        b_detail = client.get(
            f"/v2/traces/{TRACE_ID_A.hex()}", headers=bearer(key_b.token)
        )
        assert a_detail.status_code == 200
        assert b_detail.status_code == 200
        assert a_detail.json()["project_slug"] == "proj-a"
        assert b_detail.json()["project_slug"] == "proj-b"
