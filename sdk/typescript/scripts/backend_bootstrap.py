"""Bootstrap/revoke helpers for the TypeScript SDK backend integration test.

Runs inside the backend venv against the isolated test database only (the
database name must contain "test"). Prints JSON to stdout; the plaintext key
is written to the file given by --key-file (never printed to stdout/logs).
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["create", "revoke", "cleanup"])
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--backend-dir", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--key-file", help="write the plaintext key here (create)")
    parser.add_argument("--key-prefix", help="lookup prefix of the key to revoke")
    args = parser.parse_args()

    if "test" not in (args.database_url.rsplit("/", 1)[-1]):
        print("refusing: database name does not contain 'test'", file=sys.stderr)
        return 2

    os.environ["DATABASE_URL"] = args.database_url
    sys.path.insert(0, args.backend_dir)

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(args.database_url)
    Session = sessionmaker(bind=engine)

    # Import every model module so SQLAlchemy can resolve all FK targets.
    import app.models  # noqa: F401,E402
    import app.models_identity  # noqa: F401,E402
    import app.models_otel  # noqa: F401,E402
    from app.models_auth import ProjectAPIKey  # noqa: E402
    from app.services import api_key_service  # noqa: E402

    db = Session()
    try:
        if args.command == "create":
            if not args.key_file:
                print("--key-file is required for create", file=sys.stderr)
                return 2
            project = api_key_service.get_or_create_project(db, slug=args.slug)
            created = api_key_service.create_api_key(
                db,
                project=project,
                name="ts-sdk-integration",
                scopes=["traces:ingest", "traces:read"],
            )
            db.commit()
            with open(args.key_file, "w") as fh:
                fh.write(created.token)
            os.chmod(args.key_file, 0o600)
            print(
                json.dumps(
                    {
                        "project_id": str(project.id),
                        "project_slug": project.slug,
                        "key_prefix": created.api_key.key_prefix,
                    }
                )
            )
            return 0

        if args.command == "cleanup":
            # Remove the integration project and everything scoped to it.
            from sqlalchemy import delete, select as sa_select

            from app.models import Project
            from app.models_otel import OtelSpan, OtelTrace

            project = db.scalar(sa_select(Project).where(Project.slug == args.slug))
            if project is not None:
                db.execute(delete(OtelSpan).where(OtelSpan.project_id == project.id))
                db.execute(delete(OtelTrace).where(OtelTrace.project_id == project.id))
                db.execute(
                    delete(ProjectAPIKey).where(ProjectAPIKey.project_id == project.id)
                )
                db.delete(project)
                db.commit()
            print(json.dumps({"cleaned": args.slug}))
            return 0

        if not args.key_prefix:
            print("--key-prefix is required for revoke", file=sys.stderr)
            return 2
        key = db.scalar(
            select(ProjectAPIKey).where(ProjectAPIKey.key_prefix == args.key_prefix)
        )
        if key is None:
            print("key not found", file=sys.stderr)
            return 1
        api_key_service.revoke_api_key(db, api_key=key)
        db.commit()
        print(json.dumps({"revoked": args.key_prefix}))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
