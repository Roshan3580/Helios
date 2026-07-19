"""Self-serve project API-key list/create/revoke via /v2/user routes."""

from __future__ import annotations

import uuid

from app.models_auth import ProjectAPIKey
from app.security.api_keys import hash_token
from app.services import api_key_service, organization_service, user_project_service
from otlp_helpers import make_request, nested_trace_spans, post_otlp
from workos_helpers import bearer, make_token

OTHER_ORG = "org_01OTHERORGKEYS00000000001"


def _headers():
    return bearer(make_token())


def _create_org_project(db_session, linked_org, *, slug: str, name: str = "P"):
    return user_project_service.create_project_for_organization(
        db_session, organization=linked_org, name=name, slug=slug
    )


class TestListKeys:
    def test_authorized_list(
        self, client, db_session, workos_verifier, linked_org
    ):
        project = _create_org_project(db_session, linked_org, slug="list-keys")
        created = api_key_service.create_api_key(
            db_session,
            project=project,
            name="dev",
            scopes=["traces:ingest", "traces:read"],
        )
        db_session.commit()
        response = client.get(
            f"/v2/user/projects/{project.id}/api-keys", headers=_headers()
        )
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 1
        row = rows[0]
        assert row["name"] == "dev"
        assert row["status"] == "active"
        assert row["key_identifier"].startswith("hel_proj_")
        assert row["key_identifier"].endswith("…")
        assert created.token not in str(rows)
        assert created.api_key.key_hash not in str(rows)
        assert "key_hash" not in row
        assert "plaintext_key" not in row
        assert "token" not in row

    def test_ordering_active_before_revoked_newest_first(
        self, client, db_session, workos_verifier, linked_org
    ):
        project = _create_org_project(db_session, linked_org, slug="order-keys")
        older = api_key_service.create_api_key(
            db_session, project=project, name="older", scopes=["traces:read"]
        )
        newer = api_key_service.create_api_key(
            db_session, project=project, name="newer", scopes=["traces:read"]
        )
        api_key_service.revoke_api_key(db_session, api_key=older.api_key)
        db_session.commit()
        rows = client.get(
            f"/v2/user/projects/{project.slug}/api-keys", headers=_headers()
        ).json()
        assert [r["name"] for r in rows] == ["newer", "older"]
        assert rows[0]["status"] == "active"
        assert rows[1]["status"] == "revoked"
        assert rows[0]["id"] == str(newer.api_key.id)

    def test_cross_org_project_404(
        self, client, db_session, workos_verifier, linked_org
    ):
        other, _ = organization_service.create_organization(
            db_session,
            workos_org_id=OTHER_ORG,
            slug="other-keys",
            name="Other",
        )
        project = _create_org_project(db_session, linked_org, slug="mine-keys")
        db_session.commit()
        response = client.get(
            f"/v2/user/projects/{project.id}/api-keys",
            headers=bearer(make_token(org_id=OTHER_ORG)),
        )
        assert response.status_code == 404
        assert other.id is not None

    def test_project_api_key_on_human_endpoint_401(
        self, client, db_session, workos_verifier, linked_org
    ):
        project = _create_org_project(db_session, linked_org, slug="human-guard")
        key = api_key_service.create_api_key(
            db_session,
            project=project,
            name="m",
            scopes=["traces:ingest", "traces:read"],
        )
        db_session.commit()
        response = client.get(
            f"/v2/user/projects/{project.id}/api-keys",
            headers={"Authorization": f"Bearer {key.token}"},
        )
        assert response.status_code == 401

    def test_keys_from_other_project_absent(
        self, client, db_session, workos_verifier, linked_org
    ):
        a = _create_org_project(db_session, linked_org, slug="proj-a-keys")
        b = _create_org_project(db_session, linked_org, slug="proj-b-keys")
        api_key_service.create_api_key(
            db_session, project=a, name="a-key", scopes=["traces:read"]
        )
        api_key_service.create_api_key(
            db_session, project=b, name="b-key", scopes=["traces:read"]
        )
        db_session.commit()
        rows = client.get(
            f"/v2/user/projects/{a.id}/api-keys", headers=_headers()
        ).json()
        assert [r["name"] for r in rows] == ["a-key"]


class TestCreateKey:
    def test_successful_creation_and_one_time_plaintext(
        self, client, db_session, workos_verifier, linked_org
    ):
        project = _create_org_project(db_session, linked_org, slug="create-key")
        db_session.commit()
        response = client.post(
            f"/v2/user/projects/{project.id}/api-keys",
            json={
                "name": " Local development ",
                "scopes": ["traces:ingest", "traces:read", "traces:ingest"],
            },
            headers=_headers(),
        )
        assert response.status_code == 201
        body = response.json()
        plaintext = body["plaintext_key"]
        assert plaintext.startswith("hel_proj_")
        assert body["key"]["name"] == "Local development"
        assert body["key"]["scopes"] == ["traces:ingest", "traces:read"]
        assert body["key"]["status"] == "active"
        # DB stores hash, not plaintext.
        stored = db_session.get(ProjectAPIKey, uuid.UUID(body["key"]["id"]))
        assert stored is not None
        assert stored.key_hash == hash_token(plaintext)
        assert plaintext not in stored.key_hash
        assert stored.key_prefix == plaintext.split("_")[2]
        # List never returns plaintext or hash.
        listed = client.get(
            f"/v2/user/projects/{project.id}/api-keys", headers=_headers()
        ).json()
        payload = str(listed)
        assert plaintext not in payload
        assert stored.key_hash not in payload
        assert "plaintext_key" not in listed[0]

    def test_two_keys_differ(self, client, db_session, workos_verifier, linked_org):
        project = _create_org_project(db_session, linked_org, slug="two-keys")
        db_session.commit()
        a = client.post(
            f"/v2/user/projects/{project.id}/api-keys",
            json={"name": "a", "scopes": ["traces:read"]},
            headers=_headers(),
        ).json()
        b = client.post(
            f"/v2/user/projects/{project.id}/api-keys",
            json={"name": "b", "scopes": ["traces:read"]},
            headers=_headers(),
        ).json()
        assert a["plaintext_key"] != b["plaintext_key"]
        assert a["key"]["id"] != b["key"]["id"]

    def test_unknown_scope_422(self, client, db_session, workos_verifier, linked_org):
        project = _create_org_project(db_session, linked_org, slug="bad-scope")
        db_session.commit()
        response = client.post(
            f"/v2/user/projects/{project.id}/api-keys",
            json={"name": "x", "scopes": ["traces:admin"]},
            headers=_headers(),
        )
        assert response.status_code == 422

    def test_empty_scopes_422(self, client, db_session, workos_verifier, linked_org):
        project = _create_org_project(db_session, linked_org, slug="empty-scope")
        db_session.commit()
        response = client.post(
            f"/v2/user/projects/{project.id}/api-keys",
            json={"name": "x", "scopes": []},
            headers=_headers(),
        )
        assert response.status_code == 422

    def test_blank_name_422(self, client, db_session, workos_verifier, linked_org):
        project = _create_org_project(db_session, linked_org, slug="blank-name")
        db_session.commit()
        response = client.post(
            f"/v2/user/projects/{project.id}/api-keys",
            json={"name": "  ", "scopes": ["traces:read"]},
            headers=_headers(),
        )
        assert response.status_code == 422

    def test_client_supplied_secret_fields_rejected(
        self, client, db_session, workos_verifier, linked_org
    ):
        project = _create_org_project(db_session, linked_org, slug="no-override")
        db_session.commit()
        response = client.post(
            f"/v2/user/projects/{project.id}/api-keys",
            json={
                "name": "x",
                "scopes": ["traces:read"],
                "plaintext_key": "hel_proj_deadbeef_secret",
                "key_hash": "abc",
                "id": str(uuid.uuid4()),
            },
            headers=_headers(),
        )
        assert response.status_code == 422

    def test_plaintext_authenticates_machine_routes(
        self, client, db_session, workos_verifier, linked_org
    ):
        project = _create_org_project(db_session, linked_org, slug="auth-key")
        db_session.commit()
        created = client.post(
            f"/v2/user/projects/{project.id}/api-keys",
            json={
                "name": "both",
                "scopes": ["traces:ingest", "traces:read"],
            },
            headers=_headers(),
        ).json()
        token = created["plaintext_key"]
        ingest = post_otlp(
            client, make_request(nested_trace_spans()), token=token
        )
        assert ingest.status_code == 200
        reads = client.get(
            "/v2/traces", headers={"Authorization": f"Bearer {token}"}
        )
        assert reads.status_code == 200

    def test_scope_enforcement_ingest_only(
        self, client, db_session, workos_verifier, linked_org
    ):
        project = _create_org_project(db_session, linked_org, slug="ingest-only")
        db_session.commit()
        created = client.post(
            f"/v2/user/projects/{project.id}/api-keys",
            json={"name": "ingest", "scopes": ["traces:ingest"]},
            headers=_headers(),
        ).json()
        token = created["plaintext_key"]
        assert (
            post_otlp(
                client, make_request(nested_trace_spans()), token=token
            ).status_code
            == 200
        )
        reads = client.get(
            "/v2/traces", headers={"Authorization": f"Bearer {token}"}
        )
        assert reads.status_code == 403

    def test_scope_enforcement_read_only(
        self, client, db_session, workos_verifier, linked_org
    ):
        project = _create_org_project(db_session, linked_org, slug="read-only")
        db_session.commit()
        created = client.post(
            f"/v2/user/projects/{project.id}/api-keys",
            json={"name": "read", "scopes": ["traces:read"]},
            headers=_headers(),
        ).json()
        token = created["plaintext_key"]
        assert (
            post_otlp(
                client, make_request(nested_trace_spans()), token=token
            ).status_code
            == 403
        )
        reads = client.get(
            "/v2/traces", headers={"Authorization": f"Bearer {token}"}
        )
        assert reads.status_code == 200


class TestRevoke:
    def test_revoke_blocks_machine_auth(
        self, client, db_session, workos_verifier, linked_org
    ):
        project = _create_org_project(db_session, linked_org, slug="revoke-key")
        db_session.commit()
        created = client.post(
            f"/v2/user/projects/{project.id}/api-keys",
            json={
                "name": "temp",
                "scopes": ["traces:ingest", "traces:read"],
            },
            headers=_headers(),
        ).json()
        token = created["plaintext_key"]
        key_id = created["key"]["id"]
        revoked = client.post(
            f"/v2/user/projects/{project.id}/api-keys/{key_id}/revoke",
            headers=_headers(),
        )
        assert revoked.status_code == 200
        body = revoked.json()
        assert body["status"] == "revoked"
        assert body["revoked_at"] is not None
        assert "plaintext_key" not in body
        assert token not in str(body)
        assert (
            post_otlp(
                client, make_request(nested_trace_spans()), token=token
            ).status_code
            == 401
        )
        assert (
            client.get(
                "/v2/traces", headers={"Authorization": f"Bearer {token}"}
            ).status_code
            == 401
        )
        listed = client.get(
            f"/v2/user/projects/{project.id}/api-keys", headers=_headers()
        ).json()
        assert listed[0]["status"] == "revoked"
        assert token not in str(listed)

    def test_revoke_idempotent(self, client, db_session, workos_verifier, linked_org):
        project = _create_org_project(db_session, linked_org, slug="revoke-idem")
        db_session.commit()
        created = client.post(
            f"/v2/user/projects/{project.id}/api-keys",
            json={"name": "temp", "scopes": ["traces:read"]},
            headers=_headers(),
        ).json()
        key_id = created["key"]["id"]
        first = client.post(
            f"/v2/user/projects/{project.id}/api-keys/{key_id}/revoke",
            headers=_headers(),
        )
        second = client.post(
            f"/v2/user/projects/{project.id}/api-keys/{key_id}/revoke",
            headers=_headers(),
        )
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["status"] == "revoked"

    def test_revoke_other_project_key_404(
        self, client, db_session, workos_verifier, linked_org
    ):
        a = _create_org_project(db_session, linked_org, slug="rev-a")
        b = _create_org_project(db_session, linked_org, slug="rev-b")
        created = api_key_service.create_api_key(
            db_session, project=a, name="a", scopes=["traces:read"]
        )
        db_session.commit()
        response = client.post(
            f"/v2/user/projects/{b.id}/api-keys/{created.api_key.id}/revoke",
            headers=_headers(),
        )
        assert response.status_code == 404

    def test_revoke_cross_org_404(
        self, client, db_session, workos_verifier, linked_org
    ):
        organization_service.create_organization(
            db_session,
            workos_org_id=OTHER_ORG,
            slug="other-rev",
            name="Other",
        )
        project = _create_org_project(db_session, linked_org, slug="rev-cross")
        created = api_key_service.create_api_key(
            db_session, project=project, name="a", scopes=["traces:read"]
        )
        db_session.commit()
        response = client.post(
            f"/v2/user/projects/{project.id}/api-keys/{created.api_key.id}/revoke",
            headers=bearer(make_token(org_id=OTHER_ORG)),
        )
        assert response.status_code == 404

    def test_missing_key_404(self, client, db_session, workos_verifier, linked_org):
        project = _create_org_project(db_session, linked_org, slug="rev-missing")
        db_session.commit()
        response = client.post(
            f"/v2/user/projects/{project.id}/api-keys/{uuid.uuid4()}/revoke",
            headers=_headers(),
        )
        assert response.status_code == 404


class TestLeakage:
    def test_responses_exclude_sensitive_material(
        self, client, db_session, workos_verifier, linked_org
    ):
        project = _create_org_project(db_session, linked_org, slug="leak-check")
        db_session.commit()
        created = client.post(
            f"/v2/user/projects/{project.id}/api-keys",
            json={
                "name": "check",
                "scopes": ["traces:ingest", "traces:read"],
            },
            headers=_headers(),
        )
        plaintext = created.json()["plaintext_key"]
        digest = hash_token(plaintext)
        listed = client.get(
            f"/v2/user/projects/{project.id}/api-keys", headers=_headers()
        )
        revoked = client.post(
            f"/v2/user/projects/{project.id}/api-keys/"
            f"{created.json()['key']['id']}/revoke",
            headers=_headers(),
        )
        for response in (listed, revoked):
            text = response.text
            assert digest not in text
            assert plaintext not in text
            assert "OPENAI_API_KEY" not in text
            assert "WORKOS_API_KEY" not in text
            assert "WORKOS_COOKIE_PASSWORD" not in text


class TestRegressions:
    def test_alembic_head_unchanged(self, db_session):
        from sqlalchemy import text

        version = db_session.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        assert version == "004_human_identity"

    def test_human_create_does_not_break_dashboard(
        self, client, db_session, workos_verifier, linked_org
    ):
        project = client.post(
            "/v2/user/projects",
            json={"name": "Dash", "slug": "dash-proj"},
            headers=_headers(),
        ).json()
        response = client.get(
            f"/v2/user/projects/{project['id']}/dashboard",
            headers=_headers(),
        )
        assert response.status_code == 200
        assert response.json()["project_slug"] == "dash-proj"
