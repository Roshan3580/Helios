#!/usr/bin/env python3
"""Bootstrap linked WorkOS organizations for Helios browser E2E."""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


def reset_and_migrate(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))

    # alembic/env.py reads Settings.database_url via get_settings() (cached).
    os.environ["DATABASE_URL"] = database_url
    from app.config import get_settings

    get_settings.cache_clear()

    cfg = Config(os.path.join(BACKEND, "alembic.ini"))
    prev = os.getcwd()
    os.chdir(BACKEND)
    try:
        command.upgrade(cfg, "head")
    finally:
        os.chdir(prev)


def ensure_org(database_url: str, workos_org_id: str, slug: str, name: str) -> None:
    from app.services import organization_service

    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        organization_service.create_organization(
            db, workos_org_id=workos_org_id, slug=slug, name=name
        )
        db.commit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--org-a", required=True)
    parser.add_argument("--org-b", required=True)
    args = parser.parse_args()
    reset_and_migrate(args.database_url)
    ensure_org(args.database_url, args.org_a, "e2e-org-a", "E2E Org A")
    ensure_org(args.database_url, args.org_b, "e2e-org-b", "E2E Org B")
    print("e2e bootstrap complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
