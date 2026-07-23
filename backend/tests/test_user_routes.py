"""Human-authenticated /v2/user routes: identity, organizations, isolation."""

import pytest

from app.models_identity import User
from app.services import api_key_service, organization_service

from otlp_helpers import (
    TRACE_ID_A,
    TRACE_ID_B,
    make_request,
    make_span,
    nested_trace_spans,
    post_otlp,
)
from workos_helpers import DEFAULT_ORG, DEFAULT_SUB, bearer, make_token


def _seed_project_with_trace(db_session, client, *, slug: str, org=None):
    """Create a project (+optional org assignment) and ingest one OTel trace."""
    project = api_key_service.get_or_create_project(db_session, slug=slug)
    key = api_key_service.create_api_key(
        db_session, project=project, name="seed", scopes=["traces:ingest"]
    )
    if org is not None:
        organization_service.assign_project(
            db_session, organization=org, project_slug=slug
        )
    db_session.commit()
    response = post_otlp(client, make_request(nested_trace_spans()), token=key.token)
    assert response.status_code == 200
    return project


class TestIdentity:
    def test_jit_user_created(self, client, db_session, workos_verifier):
        assert db_session.query(User).count() == 0
        response = client.get("/v2/user/me", headers=bearer(make_token()))
        assert response.status_code == 200
        db_session.expire_all()
        user = db_session.query(User).one()
        assert user.workos_user_id == DEFAULT_SUB
        assert user.first_seen_at is not None

    def test_existing_user_last_seen_updated(self, client, db_session, workos_verifier):
        client.get("/v2/user/me", headers=bearer(make_token()))
        db_session.expire_all()
        first_seen = db_session.query(User).one().last_seen_at

        client.get("/v2/user/me", headers=bearer(make_token()))
        db_session.expire_all()
        assert db_session.query(User).count() == 1
        assert db_session.query(User).one().last_seen_at >= first_seen

    def test_me_without_org_reports_unlinked(self, client, workos_verifier):
        body = client.get(
            "/v2/user/me", headers=bearer(make_token(org_id=None))
        ).json()
        assert body["organization"]["linked"] is False
        assert body["organization"]["workos_org_id"] is None

    def test_me_returns_browser_safe_fields_only(self, client, workos_verifier, linked_org):
        token = make_token(permissions=["traces:read"])
        body = client.get("/v2/user/me", headers=bearer(token)).json()
        assert body["workos_user_id"] == DEFAULT_SUB
        assert body["organization"]["slug"] == "test-org"
        assert body["organization"]["linked"] is True
        assert body["role"] == "member"
        assert body["permissions"] == ["traces:read"]
        # No token or credential material in the response.
        assert token not in str(body)

    def test_missing_token_401(self, client, workos_verifier):
        response = client.get("/v2/user/me")
        assert response.status_code == 401
        assert response.headers.get("www-authenticate") == "Bearer"

    def test_invalid_token_401(self, client, workos_verifier):
        response = client.get("/v2/user/me", headers=bearer("garbage"))
        assert response.status_code == 401


class TestOrganizationScoping:
    def test_new_org_is_auto_bootstrapped(self, client, db_session, workos_verifier):
        # Checkpoint 24: a valid JWT with a not-yet-seen (but plausible) org_id
        # is mapped to a local organization automatically — no admin CLI step.
        # The org is scoped to itself: it owns no projects until it creates one.
        from app.models_identity import Organization

        response = client.get(
            "/v2/user/projects",
            headers=bearer(make_token(org_id="org_01BRANDNEWORG0000000001")),
        )
        assert response.status_code == 200
        assert response.json() == []
        db_session.expire_all()
        org = (
            db_session.query(Organization)
            .filter_by(workos_org_id="org_01BRANDNEWORG0000000001")
            .one()
        )
        assert org.slug  # a unique slug was derived from the verified org id

    def test_missing_org_id_on_org_route_403(self, client, workos_verifier):
        response = client.get(
            "/v2/user/projects", headers=bearer(make_token(org_id=None))
        )
        assert response.status_code == 403

    def test_linked_org_lists_only_its_projects(
        self, client, db_session, workos_verifier, linked_org
    ):
        _seed_project_with_trace(db_session, client, slug="org-project", org=linked_org)
        _seed_project_with_trace(db_session, client, slug="other-project")  # unassigned

        rows = client.get("/v2/user/projects", headers=bearer(make_token())).json()

        assert [row["slug"] for row in rows] == ["org-project"]
        assert set(rows[0].keys()) == {"id", "slug", "name", "environment"}

    def test_project_cannot_join_two_organizations(self, db_session, linked_org):
        org2, _ = organization_service.create_organization(
            db_session,
            workos_org_id="org_01SECONDORG000000000000",
            slug="second-org",
            name="Second",
        )
        api_key_service.get_or_create_project(db_session, slug="contested")
        organization_service.assign_project(
            db_session, organization=linked_org, project_slug="contested"
        )
        with pytest.raises(ValueError, match="already assigned"):
            organization_service.assign_project(
                db_session, organization=org2, project_slug="contested"
            )

    def test_api_key_still_valid_after_assignment(
        self, client, db_session, workos_verifier, linked_org
    ):
        project = api_key_service.get_or_create_project(db_session, slug="keyed")
        key = api_key_service.create_api_key(
            db_session, project=project, name="k", scopes=["traces:ingest", "traces:read"]
        )
        db_session.commit()
        organization_service.assign_project(
            db_session, organization=linked_org, project_slug="keyed"
        )
        db_session.commit()
        # Machine path unaffected by human/organization mapping.
        assert post_otlp(client, make_request([make_span()]), token=key.token).status_code == 200
        assert client.get(
            "/v2/traces", headers={"Authorization": f"Bearer {key.token}"}
        ).status_code == 200


class TestUserTraceRoutes:
    def test_trace_list_and_detail_for_authorized_project(
        self, client, db_session, workos_verifier, linked_org
    ):
        project = _seed_project_with_trace(
            db_session, client, slug="org-traces", org=linked_org
        )
        token = make_token()

        rows = client.get(
            f"/v2/user/projects/{project.id}/traces", headers=bearer(token)
        ).json()
        assert len(rows) == 1
        assert rows[0]["trace_id"] == TRACE_ID_A.hex()
        assert rows[0]["span_count"] == 3

        # By slug as well.
        detail = client.get(
            f"/v2/user/projects/org-traces/traces/{TRACE_ID_A.hex()}",
            headers=bearer(token),
        ).json()
        assert detail["trace_id"] == TRACE_ID_A.hex()
        assert [s["name"] for s in detail["spans"]] == [
            "agent.run",
            "retriever.search",
            "tool.lookup",
        ]
        # No fabricated GenAI fields.
        for forbidden in ("user_query", "model", "total_tokens", "estimated_cost_usd"):
            assert forbidden not in detail

    def test_filters_preserved(self, client, db_session, workos_verifier, linked_org):
        _seed_project_with_trace(db_session, client, slug="filtered", org=linked_org)
        rows = client.get(
            "/v2/user/projects/filtered/traces",
            params={"has_errors": "true"},
            headers=bearer(make_token()),
        ).json()
        assert len(rows) == 1  # nested_trace_spans has one error span

    def test_cross_org_project_404(self, client, db_session, workos_verifier, linked_org):
        org2, _ = organization_service.create_organization(
            db_session,
            workos_org_id="org_01SECONDORG000000000000",
            slug="second-org",
            name="Second",
        )
        db_session.commit()
        _seed_project_with_trace(db_session, client, slug="theirs", org=org2)

        # Token for the default (linked_org) organization.
        response = client.get(
            "/v2/user/projects/theirs/traces", headers=bearer(make_token())
        )
        assert response.status_code == 404

    def test_cross_org_trace_404(self, client, db_session, workos_verifier, linked_org):
        org2, _ = organization_service.create_organization(
            db_session,
            workos_org_id="org_01SECONDORG000000000000",
            slug="second-org",
            name="Second",
        )
        db_session.commit()
        _seed_project_with_trace(db_session, client, slug="theirs", org=org2)
        _seed_project_with_trace(db_session, client, slug="mine", org=linked_org)

        # The trace exists in 'theirs' but must not resolve through 'mine'.
        response = client.get(
            f"/v2/user/projects/theirs/traces/{TRACE_ID_A.hex()}",
            headers=bearer(make_token()),
        )
        assert response.status_code == 404

    def test_same_trace_id_isolated_between_org_projects(
        self, client, db_session, workos_verifier, linked_org
    ):
        _seed_project_with_trace(db_session, client, slug="proj-one", org=linked_org)
        _seed_project_with_trace(db_session, client, slug="proj-two", org=linked_org)

        token = make_token()
        one = client.get(
            f"/v2/user/projects/proj-one/traces/{TRACE_ID_A.hex()}", headers=bearer(token)
        ).json()
        two = client.get(
            f"/v2/user/projects/proj-two/traces/{TRACE_ID_A.hex()}", headers=bearer(token)
        ).json()
        assert one["project_slug"] == "proj-one"
        assert two["project_slug"] == "proj-two"

    def test_missing_trace_404(self, client, db_session, workos_verifier, linked_org):
        _seed_project_with_trace(db_session, client, slug="hastraces", org=linked_org)
        response = client.get(
            "/v2/user/projects/hastraces/traces/ffffffffffffffffffffffffffffffff",
            headers=bearer(make_token()),
        )
        assert response.status_code == 404

    def test_machine_v2_traces_unchanged(self, client, db_session, workos_verifier, linked_org):
        """A human JWT cannot use the machine route; the API-key route ignores JWTs."""
        response = client.get("/v2/traces", headers=bearer(make_token()))
        assert response.status_code == 401  # not a project API key


class TestCli:
    def test_create_assign_list(self, db_session, capsys):
        from app.cli import organizations as cli

        rc = cli.main(
            [
                "create",
                "--workos-org-id",
                "org_01CLITESTORG000000000000",
                "--slug",
                "cli-org",
                "--name",
                "CLI Org",
            ]
        )
        assert rc == 0
        assert "Created" in capsys.readouterr().out

        api_key_service.get_or_create_project(db_session, slug="cli-project")
        db_session.commit()

        rc = cli.main(
            [
                "assign-project",
                "--workos-org-id",
                "org_01CLITESTORG000000000000",
                "--project-slug",
                "cli-project",
            ]
        )
        assert rc == 0
        assert "Assigned" in capsys.readouterr().out

        # Idempotent re-assign.
        rc = cli.main(
            [
                "assign-project",
                "--workos-org-id",
                "org_01CLITESTORG000000000000",
                "--project-slug",
                "cli-project",
            ]
        )
        assert rc == 0
        assert "Already assigned" in capsys.readouterr().out

        rc = cli.main(["list"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "cli-org" in out
        assert "cli-project" in out

    def test_create_rejects_bad_workos_id(self, capsys):
        from app.cli import organizations as cli

        rc = cli.main(
            ["create", "--workos-org-id", "not-an-org-id", "--slug", "x", "--name", "X"]
        )
        assert rc == 2
        assert "does not look like" in capsys.readouterr().err

    def test_create_is_idempotent_for_same_workos_id(self, db_session, capsys):
        from app.cli import organizations as cli

        args = ["create", "--workos-org-id", "org_01IDEMPOTENT00000000000", "--slug", "idem", "--name", "Idem"]
        assert cli.main(args) == 0
        capsys.readouterr()
        assert cli.main(args) == 0
        assert "Already exists" in capsys.readouterr().out
