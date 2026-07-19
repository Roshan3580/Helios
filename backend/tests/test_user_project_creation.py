"""Self-serve project creation via POST /v2/user/projects."""

from __future__ import annotations

import uuid

from app.models import Project
from app.services import api_key_service, organization_service
from workos_helpers import DEFAULT_ORG, bearer, make_token


OTHER_ORG = "org_01OTHERORG000000000000001"


def _headers():
    return bearer(make_token())


class TestAuthGuards:
    def test_missing_jwt_401(self, client, workos_verifier):
        response = client.post(
            "/v2/user/projects", json={"name": "A", "slug": "a"}
        )
        assert response.status_code == 401

    def test_malformed_jwt_401(self, client, workos_verifier):
        response = client.post(
            "/v2/user/projects",
            json={"name": "A", "slug": "a"},
            headers=bearer("not-a-jwt"),
        )
        assert response.status_code == 401

    def test_project_api_key_401(self, client, db_session, workos_verifier, linked_org):
        project = api_key_service.get_or_create_project(db_session, slug="machine-proj")
        key = api_key_service.create_api_key(
            db_session,
            project=project,
            name="m",
            scopes=["traces:ingest", "traces:read"],
        )
        db_session.commit()
        response = client.post(
            "/v2/user/projects",
            json={"name": "A", "slug": "a-new"},
            headers={"Authorization": f"Bearer {key.token}"},
        )
        assert response.status_code == 401

    def test_unlinked_org_403(self, client, workos_verifier):
        response = client.post(
            "/v2/user/projects",
            json={"name": "A", "slug": "a"},
            headers=bearer(make_token(org_id="org_01UNLINKEDORG00000000000")),
        )
        assert response.status_code == 403


class TestCreateProject:
    def test_successful_creation(
        self, client, db_session, workos_verifier, linked_org
    ):
        response = client.post(
            "/v2/user/projects",
            json={"name": " Production Agent ", "slug": "production-agent"},
            headers=_headers(),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Production Agent"
        assert body["slug"] == "production-agent"
        assert body["environment"] == "production"
        assert uuid.UUID(body["id"])
        assert "organization_id" not in body
        # Appears in subsequent list.
        listed = client.get("/v2/user/projects", headers=_headers()).json()
        assert any(row["slug"] == "production-agent" for row in listed)
        stored = db_session.get(Project, uuid.UUID(body["id"]))
        assert stored is not None
        assert stored.organization_id == linked_org.id

    def test_environment_accepted(
        self, client, db_session, workos_verifier, linked_org
    ):
        response = client.post(
            "/v2/user/projects",
            json={
                "name": "Staging",
                "slug": "staging-agent",
                "environment": "staging",
            },
            headers=_headers(),
        )
        assert response.status_code == 201
        assert response.json()["environment"] == "staging"

    def test_duplicate_slug_same_org_409(
        self, client, db_session, workos_verifier, linked_org
    ):
        first = client.post(
            "/v2/user/projects",
            json={"name": "One", "slug": "dup-slug"},
            headers=_headers(),
        )
        assert first.status_code == 201
        second = client.post(
            "/v2/user/projects",
            json={"name": "Two", "slug": "dup-slug"},
            headers=_headers(),
        )
        assert second.status_code == 409
        assert "already exists" in second.json()["detail"]
        assert "uq_" not in second.json()["detail"].lower()
        assert "IntegrityError" not in second.json()["detail"]

    def test_duplicate_slug_other_org_also_409(
        self, client, db_session, workos_verifier, linked_org
    ):
        # Slug uniqueness is global today.
        other, _ = organization_service.create_organization(
            db_session,
            workos_org_id=OTHER_ORG,
            slug="other-org",
            name="Other Org",
        )
        db_session.commit()
        assert (
            client.post(
                "/v2/user/projects",
                json={"name": "One", "slug": "shared-slug"},
                headers=_headers(),
            ).status_code
            == 201
        )
        response = client.post(
            "/v2/user/projects",
            json={"name": "Two", "slug": "shared-slug"},
            headers=bearer(make_token(org_id=OTHER_ORG)),
        )
        assert response.status_code == 409


class TestValidation:
    def test_blank_name_rejected(self, client, workos_verifier, linked_org):
        response = client.post(
            "/v2/user/projects",
            json={"name": "   ", "slug": "ok-slug"},
            headers=_headers(),
        )
        assert response.status_code == 422

    def test_blank_slug_rejected(self, client, workos_verifier, linked_org):
        response = client.post(
            "/v2/user/projects",
            json={"name": "Ok", "slug": "  "},
            headers=_headers(),
        )
        assert response.status_code == 422

    def test_uppercase_slug_normalized(
        self, client, workos_verifier, linked_org
    ):
        response = client.post(
            "/v2/user/projects",
            json={"name": "Ok", "slug": "My-Agent"},
            headers=_headers(),
        )
        assert response.status_code == 201
        assert response.json()["slug"] == "my-agent"

    def test_underscores_rejected(self, client, workos_verifier, linked_org):
        response = client.post(
            "/v2/user/projects",
            json={"name": "Ok", "slug": "bad_slug"},
            headers=_headers(),
        )
        assert response.status_code == 422

    def test_leading_hyphen_rejected(self, client, workos_verifier, linked_org):
        response = client.post(
            "/v2/user/projects",
            json={"name": "Ok", "slug": "-bad"},
            headers=_headers(),
        )
        assert response.status_code == 422

    def test_trailing_hyphen_rejected(self, client, workos_verifier, linked_org):
        response = client.post(
            "/v2/user/projects",
            json={"name": "Ok", "slug": "bad-"},
            headers=_headers(),
        )
        assert response.status_code == 422

    def test_consecutive_hyphens_rejected(
        self, client, workos_verifier, linked_org
    ):
        response = client.post(
            "/v2/user/projects",
            json={"name": "Ok", "slug": "bad--slug"},
            headers=_headers(),
        )
        assert response.status_code == 422

    def test_max_length_name(self, client, workos_verifier, linked_org):
        response = client.post(
            "/v2/user/projects",
            json={"name": "x" * 256, "slug": "ok-len"},
            headers=_headers(),
        )
        assert response.status_code == 422

    def test_extra_fields_rejected(self, client, workos_verifier, linked_org):
        response = client.post(
            "/v2/user/projects",
            json={
                "name": "Ok",
                "slug": "extra-fields",
                "id": str(uuid.uuid4()),
                "organization_id": str(uuid.uuid4()),
            },
            headers=_headers(),
        )
        assert response.status_code == 422

    def test_query_organization_override_ignored(
        self, client, db_session, workos_verifier, linked_org
    ):
        other, _ = organization_service.create_organization(
            db_session,
            workos_org_id=OTHER_ORG,
            slug="other-org-q",
            name="Other",
        )
        db_session.commit()
        response = client.post(
            f"/v2/user/projects?organization_id={other.id}",
            json={"name": "Owned", "slug": "owned-by-jwt-org"},
            headers=_headers(),
        )
        assert response.status_code == 201
        stored = db_session.get(Project, uuid.UUID(response.json()["id"]))
        assert stored.organization_id == linked_org.id
        assert stored.organization_id != other.id

    def test_body_organization_override_rejected(
        self, client, workos_verifier, linked_org
    ):
        response = client.post(
            "/v2/user/projects",
            json={
                "name": "Ok",
                "slug": "body-org",
                "organization_id": str(uuid.uuid4()),
            },
            headers=_headers(),
        )
        assert response.status_code == 422

    def test_reserved_slug_rejected(self, client, workos_verifier, linked_org):
        response = client.post(
            "/v2/user/projects",
            json={"name": "Ok", "slug": "settings"},
            headers=_headers(),
        )
        assert response.status_code == 422


class TestIsolation:
    def test_other_org_cannot_see_created_project(
        self, client, db_session, workos_verifier, linked_org
    ):
        organization_service.create_organization(
            db_session,
            workos_org_id=OTHER_ORG,
            slug="other-iso",
            name="Other",
        )
        db_session.commit()
        created = client.post(
            "/v2/user/projects",
            json={"name": "Private", "slug": "private-proj"},
            headers=_headers(),
        ).json()
        other_list = client.get(
            "/v2/user/projects",
            headers=bearer(make_token(org_id=OTHER_ORG)),
        ).json()
        assert all(row["id"] != created["id"] for row in other_list)
