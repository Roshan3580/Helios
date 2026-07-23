"""Checkpoint 24: self-serve local organization/identity bootstrap.

Covers the security and idempotency contract of ``identity_bootstrap`` and its
effect on the human (WorkOS JWT) routes:

- a first user in a plausible WorkOS org maps only that org (A vs B isolation)
- existing organizations are reused (idempotent), never duplicated
- concurrent bootstrap calls converge on a single org / single identity
- an implausible org id is refused (no junk org is materialized)
- an invalid JWT cannot bootstrap anything
- a project API key cannot bootstrap a human organization
- a client cannot influence which organization is used (only the verified
  token's org_id is authoritative)
- cross-organization resources still return a safe 404
"""

from __future__ import annotations

import threading

import pytest

from app.models import Project
from app.models_identity import Organization, User
from app.services import api_key_service, identity_bootstrap

from otlp_helpers import make_request, nested_trace_spans, post_otlp
from workos_helpers import bearer, make_token

ORG_A = "org_01BOOTSTRAPORGA000000001"
ORG_B = "org_01BOOTSTRAPORGB000000001"


class TestBootstrapService:
    def test_organization_created_and_reused(self, db_session):
        first = identity_bootstrap.bootstrap_organization(ORG_A)
        assert first is not None
        second = identity_bootstrap.bootstrap_organization(ORG_A)
        assert second is not None
        assert first.id == second.id  # idempotent: same local row
        db_session.expire_all()
        assert (
            db_session.query(Organization).filter_by(workos_org_id=ORG_A).count() == 1
        )

    def test_existing_organization_slug_preserved(self, db_session):
        from app.services import organization_service

        existing, created = organization_service.create_organization(
            db_session, workos_org_id=ORG_A, slug="chosen-slug", name="Chosen"
        )
        db_session.commit()
        assert created
        result = identity_bootstrap.bootstrap_organization(ORG_A)
        assert result is not None
        assert result.slug == "chosen-slug"  # reuse, never overwrite
        assert result.name == "Chosen"

    def test_user_created_and_reused(self, db_session):
        uid1 = identity_bootstrap.bootstrap_user("user_01BOOTSTRAPUSER00000001")
        uid2 = identity_bootstrap.bootstrap_user("user_01BOOTSTRAPUSER00000001")
        assert uid1 == uid2
        db_session.expire_all()
        assert db_session.query(User).count() == 1

    def test_implausible_org_id_refused(self, db_session):
        assert identity_bootstrap.bootstrap_organization("not-an-org") is None
        assert identity_bootstrap.bootstrap_organization("") is None
        db_session.expire_all()
        assert db_session.query(Organization).count() == 0

    def test_concurrent_org_bootstrap_single_row(self, db_session):
        results: list = []
        barrier = threading.Barrier(8)

        def worker():
            barrier.wait()  # maximize contention on the same workos_org_id
            results.append(identity_bootstrap.bootstrap_organization(ORG_A))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(r is not None for r in results)
        assert len({r.id for r in results}) == 1  # all converge on one row
        db_session.expire_all()
        assert (
            db_session.query(Organization).filter_by(workos_org_id=ORG_A).count() == 1
        )

    def test_concurrent_user_bootstrap_single_identity(self, db_session):
        results: list = []
        barrier = threading.Barrier(8)
        sub = "user_01CONCURRENTUSER0000001"

        def worker():
            barrier.wait()
            results.append(identity_bootstrap.bootstrap_user(sub))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(results)) == 1  # single local user id
        db_session.expire_all()
        assert db_session.query(User).filter_by(workos_user_id=sub).count() == 1


class TestBootstrapViaHttp:
    def test_first_user_maps_only_its_own_org(
        self, client, db_session, workos_verifier
    ):
        # Two distinct orgs sign in; each maps exactly one local org.
        assert (
            client.get("/v2/user/projects", headers=bearer(make_token(org_id=ORG_A))).status_code
            == 200
        )
        assert (
            client.get("/v2/user/projects", headers=bearer(make_token(org_id=ORG_B))).status_code
            == 200
        )
        db_session.expire_all()
        assert db_session.query(Organization).filter_by(workos_org_id=ORG_A).count() == 1
        assert db_session.query(Organization).filter_by(workos_org_id=ORG_B).count() == 1

    def test_org_a_cannot_see_org_b_projects(self, client, db_session, workos_verifier):
        # Org A creates a project; Org B (bootstrapped on first request) sees none.
        client.post(
            "/v2/user/projects",
            json={"name": "A only", "slug": "a-only-proj"},
            headers=bearer(make_token(org_id=ORG_A)),
        )
        b_rows = client.get(
            "/v2/user/projects", headers=bearer(make_token(org_id=ORG_B))
        ).json()
        assert b_rows == []
        # And Org B cannot read Org A's project by slug (indistinguishable 404).
        assert (
            client.get(
                "/v2/user/projects/a-only-proj/traces",
                headers=bearer(make_token(org_id=ORG_B)),
            ).status_code
            == 404
        )

    def test_invalid_jwt_bootstraps_nothing(self, client, db_session, workos_verifier):
        response = client.get("/v2/user/projects", headers=bearer("garbage.token"))
        assert response.status_code == 401
        db_session.expire_all()
        assert db_session.query(Organization).count() == 0
        assert db_session.query(User).count() == 0

    def test_project_api_key_cannot_bootstrap_human_org(
        self, client, db_session, workos_verifier
    ):
        project = api_key_service.get_or_create_project(db_session, slug="machine")
        key = api_key_service.create_api_key(
            db_session, project=project, name="m", scopes=["traces:ingest"]
        )
        db_session.commit()
        # A machine credential on a human route is 401 and creates no org/user.
        response = client.get(
            "/v2/user/projects",
            headers={"Authorization": f"Bearer {key.token}"},
        )
        assert response.status_code == 401
        db_session.expire_all()
        assert db_session.query(Organization).count() == 0

    def test_client_cannot_override_org_via_query_or_body(
        self, client, db_session, workos_verifier
    ):
        # Org A creates a project. A request with Org A's token but an injected
        # organization_id pointing elsewhere is still scoped to Org A only.
        client.post(
            "/v2/user/projects",
            json={"name": "Scoped", "slug": "scoped-proj"},
            headers=bearer(make_token(org_id=ORG_A)),
        )
        rows = client.get(
            "/v2/user/projects?organization_id=org_01ATTACKER0000000000001",
            headers=bearer(make_token(org_id=ORG_A)),
        ).json()
        assert [r["slug"] for r in rows] == ["scoped-proj"]

    def test_missing_org_is_onboarding_boundary(self, client, workos_verifier):
        # A verified user with no active organization can reach /me (onboarding)
        # but not org-scoped routes.
        assert client.get("/v2/user/me", headers=bearer(make_token(org_id=None))).status_code == 200
        assert (
            client.get("/v2/user/projects", headers=bearer(make_token(org_id=None))).status_code
            == 403
        )

    def test_bootstrapped_org_can_ingest_and_read_its_traces(
        self, client, db_session, workos_verifier
    ):
        # End-to-end: Org A self-serves, creates a project, and reads a trace
        # ingested for that project (machine key path unchanged).
        created = client.post(
            "/v2/user/projects",
            json={"name": "E2E", "slug": "e2e-proj"},
            headers=bearer(make_token(org_id=ORG_A)),
        )
        assert created.status_code == 201
        project_id = created.json()["id"]
        key = client.post(
            f"/v2/user/projects/{project_id}/api-keys",
            json={"name": "ingest", "scopes": ["traces:ingest"]},
            headers=bearer(make_token(org_id=ORG_A)),
        )
        assert key.status_code == 201
        token = key.json()["plaintext_key"]
        assert post_otlp(client, make_request(nested_trace_spans()), token=token).status_code == 200
        rows = client.get(
            f"/v2/user/projects/{project_id}/traces",
            headers=bearer(make_token(org_id=ORG_A)),
        ).json()
        assert len(rows) == 1
