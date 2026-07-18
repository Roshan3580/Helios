"""Administrative CLI for organization mapping.

    python -m app.cli.organizations create \
        --workos-org-id org_... --slug acme --name "Acme"
    python -m app.cli.organizations assign-project \
        --workos-org-id org_... --project-slug acme
    python -m app.cli.organizations list

Local database mappings only — no WorkOS API key required or used. Uses the
normal application settings/DATABASE_URL; no production defaults are baked in.
Project API keys are never modified.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models_identity import Organization
from app.services import organization_service


def _get_org(db, workos_org_id: str) -> Organization | None:
    return db.scalar(
        select(Organization).where(Organization.workos_org_id == workos_org_id)
    )


def cmd_create(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        try:
            organization, created = organization_service.create_organization(
                db,
                workos_org_id=args.workos_org_id,
                slug=args.slug,
                name=args.name or args.slug,
            )
            db.commit()
        except ValueError as exc:
            db.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 2
        state = "Created" if created else "Already exists (unchanged)"
        print(f"{state}: organization '{organization.slug}'")
        print(f"  id:            {organization.id}")
        print(f"  workos org id: {organization.workos_org_id}")
        print(f"  name:          {organization.name}")
    return 0


def cmd_assign_project(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        organization = _get_org(db, args.workos_org_id)
        if organization is None:
            print(
                f"error: no organization linked for '{args.workos_org_id}'; "
                "run 'create' first",
                file=sys.stderr,
            )
            return 2
        try:
            project, changed = organization_service.assign_project(
                db, organization=organization, project_slug=args.project_slug
            )
            db.commit()
        except ValueError as exc:
            db.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 2
        state = "Assigned" if changed else "Already assigned (unchanged)"
        print(f"{state}: project '{project.slug}' -> organization '{organization.slug}'")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        rows = organization_service.list_organizations(db)
        if not rows:
            print("No organizations linked.")
            return 0
        for organization, projects in rows:
            print(f"[{organization.slug}] {organization.name}")
            print(f"    workos org id: {organization.workos_org_id}")
            if projects:
                for project in projects:
                    print(f"    project: {project.slug} ({project.environment})")
            else:
                print("    (no projects assigned)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="app.cli.organizations", description="Manage organization mappings"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Link a WorkOS organization to Helios")
    create.add_argument("--workos-org-id", required=True)
    create.add_argument("--slug", required=True)
    create.add_argument("--name", default=None)
    create.set_defaults(func=cmd_create)

    assign = sub.add_parser("assign-project", help="Assign a project to an organization")
    assign.add_argument("--workos-org-id", required=True)
    assign.add_argument("--project-slug", required=True)
    assign.set_defaults(func=cmd_assign_project)

    listing = sub.add_parser("list", help="List organizations and their projects")
    listing.set_defaults(func=cmd_list)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
