"""Pytest fixtures for the Helios backend test suite.

Safety model
------------
- Tests refuse to run unless HELIOS_TEST_DATABASE_URL is set and points at a
  database whose name contains "test". This makes it impossible to run the
  suite against the normal development database (`helios` on :5433) or any
  production DATABASE_URL by accident.
- DATABASE_URL is overwritten with the test URL *before* any `app` module is
  imported, so the cached settings, the app engine, and Alembic's env.py all
  resolve to the test database. Real environment variables take precedence
  over any developer `.env` file in pydantic-settings, so a local `.env`
  cannot leak its DATABASE_URL into the tests.
- The FastAPI `get_db` dependency is additionally overridden with a session
  factory bound to the test engine (belt and suspenders).
- The real Alembic migration chain is applied once per session; every test
  ends with a TRUNCATE of all application tables for isolated state.

Start the database with:
    docker compose -f docker-compose.test.yml up -d --wait
    export HELIOS_TEST_DATABASE_URL=postgresql://helios_test:helios_test@localhost:5434/helios_test
"""

import os
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

_TEST_DB_ENV = "HELIOS_TEST_DATABASE_URL"
_test_db_url = os.environ.get(_TEST_DB_ENV)

if not _test_db_url:
    raise RuntimeError(
        f"{_TEST_DB_ENV} is not set. Refusing to run backend tests without an "
        "explicit, dedicated test database.\n"
        "Start one with: docker compose -f docker-compose.test.yml up -d --wait\n"
        f"Then: export {_TEST_DB_ENV}="
        "postgresql://helios_test:helios_test@localhost:5434/helios_test"
    )

_database_name = make_url(_test_db_url).database or ""
if "test" not in _database_name:
    raise RuntimeError(
        f"{_TEST_DB_ENV} points at database '{_database_name}', whose name does "
        "not contain 'test'. Refusing to run: this looks like a development or "
        "production database."
    )

# Must happen before any `app` import so settings/engine/Alembic all see it.
os.environ["DATABASE_URL"] = _test_db_url

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]

test_engine = create_engine(_test_db_url, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)

# Application tables in FK-safe truncation order (alembic_version excluded).
_APP_TABLES = (
    "spans",
    "traces",
    "prompt_versions",
    "evaluation_runs",
    "rag_chunk_metrics",
    "projects",
)


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    """Apply the real Alembic migration chain to the test database once."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")
    yield


@pytest.fixture(autouse=True)
def clean_database(migrated_database):
    """Give every test an empty schema afterwards (isolated state)."""
    yield
    with test_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {', '.join(_APP_TABLES)} CASCADE"))


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client():
    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def db_session():
    """Direct session against the test database for persistence assertions."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
