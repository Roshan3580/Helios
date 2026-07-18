"""Administrative CLI for project API keys.

    python -m app.cli.api_keys create --project-slug <slug> --name <name> \
        --scopes traces:ingest,traces:read [--project-name ..] [--environment ..] \
        [--expires-at 2026-12-31T00:00:00Z]
    python -m app.cli.api_keys list --project-slug <slug>
    python -m app.cli.api_keys revoke --key-id <uuid> | --key-prefix <prefix>

Uses the normal application settings and DB session (DATABASE_URL). It connects
to production only if the operator explicitly points DATABASE_URL there; no
production defaults or credentials are baked in.

The full plaintext key is printed exactly once by `create` and can never be
retrieved again.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Project
from app.models_auth import ProjectAPIKey
from app.services import api_key_service


def _parse_expires_at(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _fmt(dt: datetime | None) -> str:
    return dt.isoformat() if dt else "-"


def _key_status(key: ProjectAPIKey, now: datetime) -> str:
    if key.revoked_at is not None:
        return "revoked"
    if key.expires_at is not None and key.expires_at <= now:
        return "expired"
    return "active"


def cmd_create(args: argparse.Namespace) -> int:
    scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]
    try:
        expires_at = _parse_expires_at(args.expires_at)
    except ValueError:
        print(f"error: invalid --expires-at value: {args.expires_at!r}", file=sys.stderr)
        return 2

    with SessionLocal() as db:
        try:
            project = api_key_service.get_or_create_project(
                db,
                slug=args.project_slug,
                name=args.project_name,
                environment=args.environment or "production",
            )
            created = api_key_service.create_api_key(
                db,
                project=project,
                name=args.name,
                scopes=scopes,
                expires_at=expires_at,
            )
            db.commit()
        except ValueError as exc:
            db.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 2

        key = created.api_key
        print("Created API key")
        print(f"  project:  {project.slug} ({project.name})")
        print(f"  name:     {key.name}")
        print(f"  key id:   {key.id}")
        print(f"  prefix:   {key.key_prefix}")
        print(f"  scopes:   {', '.join(key.scopes)}")
        print(f"  expires:  {_fmt(key.expires_at)}")
        print()
        print("  API KEY (shown once, cannot be retrieved later):")
        print(f"    {created.token}")
        print()
        print("  Store it securely. It is a secret; do not commit it or put it in browser code.")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        project = db.scalar(select(Project).where(Project.slug == args.project_slug))
        if project is None:
            print(f"error: project '{args.project_slug}' not found", file=sys.stderr)
            return 2
        keys = api_key_service.list_api_keys(db, project=project)
        if not keys:
            print(f"No API keys for project '{project.slug}'.")
            return 0
        print(f"API keys for project '{project.slug}':")
        for key in keys:
            print(
                f"  [{_key_status(key, now)}] {key.name}\n"
                f"      id:        {key.id}\n"
                f"      prefix:    {key.key_prefix}\n"
                f"      scopes:    {', '.join(key.scopes)}\n"
                f"      created:   {_fmt(key.created_at)}\n"
                f"      last used: {_fmt(key.last_used_at)}\n"
                f"      expires:   {_fmt(key.expires_at)}\n"
                f"      revoked:   {_fmt(key.revoked_at)}"
            )
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    if not args.key_id and not args.key_prefix:
        print("error: provide --key-id or --key-prefix", file=sys.stderr)
        return 2
    with SessionLocal() as db:
        stmt = select(ProjectAPIKey)
        if args.key_id:
            stmt = stmt.where(ProjectAPIKey.id == args.key_id)
        else:
            stmt = stmt.where(ProjectAPIKey.key_prefix == args.key_prefix)
        key = db.scalar(stmt)
        if key is None:
            print("error: API key not found", file=sys.stderr)
            return 2
        newly = api_key_service.revoke_api_key(db, api_key=key)
        db.commit()
        if newly:
            print(f"Revoked API key {key.id} (prefix {key.key_prefix}).")
        else:
            print(f"API key {key.id} (prefix {key.key_prefix}) was already revoked.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.cli.api_keys", description="Manage project API keys")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Create a new project API key")
    create.add_argument("--project-slug", required=True)
    create.add_argument("--project-name", default=None)
    create.add_argument("--environment", default=None)
    create.add_argument("--name", required=True, help="Human-readable key name")
    create.add_argument("--scopes", required=True, help="Comma-separated scopes")
    create.add_argument("--expires-at", default=None, help="ISO 8601 expiry (optional)")
    create.set_defaults(func=cmd_create)

    listing = sub.add_parser("list", help="List API keys for a project")
    listing.add_argument("--project-slug", required=True)
    listing.set_defaults(func=cmd_list)

    revoke = sub.add_parser("revoke", help="Revoke an API key")
    revoke.add_argument("--key-id", default=None)
    revoke.add_argument("--key-prefix", default=None)
    revoke.set_defaults(func=cmd_revoke)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
