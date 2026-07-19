"""Deployment contract CLI: migration head check and config validation.

Usage:
  python -m app.cli.deployment_check
  python -m app.cli.deployment_check --config-only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

from app.config import get_settings
from app.deployment_validation import sanitize_message, validate_settings


def _expected_heads() -> list[str]:
    backend_dir = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend_dir / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    return list(script.get_heads())


def _database_version(database_url: str) -> str | None:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
            return None if row is None else str(row[0])
    except Exception:
        return None
    finally:
        engine.dispose()


def run_config_check() -> int:
    settings = get_settings()
    issues = validate_settings(
        environment=settings.helios_environment,
        database_url=settings.database_url,
        cors_origins=settings.cors_origin_list,
        workos_issuer=settings.workos_issuer_resolved,
        workos_jwks_url=settings.workos_jwks_url_resolved,
        helios_e2e_test_mode=settings.helios_e2e_test_mode,
        narrative_enabled=settings.helios_analyst_narrative_enabled,
        allow_third_party=settings.helios_analyst_allow_third_party,
        analyst_provider=settings.helios_analyst_provider,
        openai_key_present=bool(settings.openai_api_key.get_secret_value()),
    )
    if issues:
        for issue in issues:
            print(f"CONFIG_FAIL {issue.code}: {sanitize_message(issue.message)}", file=sys.stderr)
        return 1
    print("CONFIG_OK")
    return 0


def run_migration_check(*, strict: bool) -> int:
    settings = get_settings()
    heads = _expected_heads()
    current = _database_version(settings.database_url)
    print(f"ALEMBIC_HEADS={','.join(heads)}")
    print(f"DATABASE_VERSION={current or 'none'}")
    if current is None:
        print("MIGRATION_STATUS=missing_or_unreachable", file=sys.stderr)
        return 1 if strict else 0
    if current not in heads:
        print("MIGRATION_STATUS=upgrade_required", file=sys.stderr)
        return 1 if strict else 0
    print("MIGRATION_STATUS=current")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Helios deployment contract checks")
    parser.add_argument(
        "--config-only",
        action="store_true",
        help="Validate environment contract without touching the database",
    )
    parser.add_argument(
        "--strict-migrations",
        action="store_true",
        help="Exit nonzero when database is not at Alembic head",
    )
    args = parser.parse_args(argv)

    code = run_config_check()
    if args.config_only:
        return code
    mig = run_migration_check(strict=args.strict_migrations)
    return code or mig


if __name__ == "__main__":
    raise SystemExit(main())
