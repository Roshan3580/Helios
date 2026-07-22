"""Tests for the API-key management service and the admin CLI.

The CLI uses app.database.SessionLocal, which (like the app) is bound to the
test database in this suite.
"""

import pytest

from app.cli import api_keys as cli
from app.models_auth import ProjectAPIKey
from app.security.api_keys import hash_token, verify_token
from app.services import api_key_service

from otlp_helpers import bearer


class TestService:
    def test_create_stores_prefix_and_hash_not_plaintext(self, db_session):
        project = api_key_service.get_or_create_project(db_session, slug="svc-proj")
        created = api_key_service.create_api_key(
            db_session, project=project, name="k", scopes=["traces:read"]
        )
        db_session.commit()

        row = db_session.get(ProjectAPIKey, created.api_key.id)
        # Plaintext token never persisted; hash matches; prefix is non-secret.
        assert row.key_hash != created.token
        assert row.key_hash == hash_token(created.token)
        assert verify_token(created.token, row.key_hash)
        assert row.key_prefix in created.token
        assert row.key_prefix != created.token

    def test_get_or_create_project_is_idempotent(self, db_session):
        p1 = api_key_service.get_or_create_project(db_session, slug="dup-proj")
        p2 = api_key_service.get_or_create_project(db_session, slug="dup-proj")
        assert p1.id == p2.id

    def test_invalid_scope_rejected(self, db_session):
        project = api_key_service.get_or_create_project(db_session, slug="bad-scope")
        with pytest.raises(ValueError):
            api_key_service.create_api_key(
                db_session, project=project, name="k", scopes=["traces:delete"]
            )

    def test_revoke_is_idempotent(self, db_session):
        project = api_key_service.get_or_create_project(db_session, slug="rev-proj")
        created = api_key_service.create_api_key(
            db_session, project=project, name="k", scopes=["traces:read"]
        )
        db_session.commit()

        assert api_key_service.revoke_api_key(db_session, api_key=created.api_key) is True
        assert api_key_service.revoke_api_key(db_session, api_key=created.api_key) is False


class TestCli:
    def test_create_prints_plaintext_key_once_with_warning(self, capsys):
        rc = cli.main(
            [
                "create",
                "--project-slug",
                "cli-create",
                "--name",
                "Local dev",
                "--scopes",
                "traces:ingest,traces:read",
            ]
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "shown once" in out
        assert "do not commit" in out.lower()
        # Exactly one full token in the output.
        assert out.count("hel_proj_") == 1

    def test_create_rejects_invalid_scope(self, capsys):
        rc = cli.main(
            ["create", "--project-slug", "cli-bad", "--name", "k", "--scopes", "nope"]
        )
        assert rc == 2
        assert "invalid scope" in capsys.readouterr().err

    def test_list_excludes_token_and_hash(self, db_session, capsys):
        project = api_key_service.get_or_create_project(db_session, slug="cli-list")
        created = api_key_service.create_api_key(
            db_session, project=project, name="listed", scopes=["traces:read"]
        )
        db_session.commit()

        rc = cli.main(["list", "--project-slug", "cli-list"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "listed" in out
        assert created.api_key.key_prefix in out
        assert created.token not in out
        assert created.api_key.key_hash not in out

    def test_list_unknown_project_errors(self, capsys):
        rc = cli.main(["list", "--project-slug", "no-such-project"])
        assert rc == 2
        assert "not found" in capsys.readouterr().err

    def test_revoke_blocks_future_authentication(self, client, db_session, capsys):
        project = api_key_service.get_or_create_project(db_session, slug="cli-revoke")
        created = api_key_service.create_api_key(
            db_session, project=project, name="k", scopes=["traces:read"]
        )
        db_session.commit()

        # Works before revocation.
        assert client.get("/v2/traces", headers=bearer(created.token)).status_code == 200

        rc = cli.main(["revoke", "--key-prefix", created.api_key.key_prefix])
        assert rc == 0
        assert "Revoked" in capsys.readouterr().out

        # 401 after revocation.
        assert client.get("/v2/traces", headers=bearer(created.token)).status_code == 401

    def test_revoke_twice_reports_already_revoked(self, db_session, capsys):
        project = api_key_service.get_or_create_project(db_session, slug="cli-revoke2")
        created = api_key_service.create_api_key(
            db_session, project=project, name="k", scopes=["traces:read"]
        )
        db_session.commit()

        cli.main(["revoke", "--key-prefix", created.api_key.key_prefix])
        capsys.readouterr()
        cli.main(["revoke", "--key-prefix", created.api_key.key_prefix])
        assert "already revoked" in capsys.readouterr().out

    def test_revoke_without_identifier_errors(self, capsys):
        rc = cli.main(["revoke"])
        assert rc == 2
        assert "key-id" in capsys.readouterr().err
