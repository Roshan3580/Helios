"""Liveness and readiness health endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.database import get_db
from app.main import app


def test_live_does_not_require_database(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok", "service": "helios-api"}
    assert "database" not in body
    assert "DATABASE_URL" not in response.text


def test_ready_succeeds_with_migrated_database(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["service"] == "helios-api"


def test_ready_fails_sanitized_when_db_unavailable(client):
    mock_db = MagicMock()
    mock_db.execute.side_effect = RuntimeError(
        "connection to postgresql://secret:pass@db/helios failed"
    )

    def _override():
        yield mock_db

    app.dependency_overrides[get_db] = _override
    try:
        response = client.get("/health/ready")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["reason"] == "database_unavailable"
    assert "postgresql://" not in response.text
    assert "secret" not in response.text


def test_ready_fails_when_migrations_missing(client):
    mock_db = MagicMock()
    version_result = MagicMock()
    version_result.fetchone.return_value = None
    mock_db.execute.side_effect = [MagicMock(), version_result]

    def _override():
        yield mock_db

    app.dependency_overrides[get_db] = _override
    try:
        response = client.get("/health/ready")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    assert response.json()["reason"] == "migrations_pending"


def test_legacy_health_still_works(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["database"] == "connected"
