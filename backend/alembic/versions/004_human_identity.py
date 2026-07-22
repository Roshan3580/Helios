"""human identity: users, organizations, project ownership

WorkOS AuthKit is the identity provider; these tables hold only the local
mapping needed for application data ownership. No passwords, password hashes,
refresh tokens, or WorkOS API keys are ever stored.

projects.organization_id is nullable so existing projects migrate safely and
are assigned to organizations explicitly via the admin CLI (no unsafe global
backfill assumption).

Revision ID: 004_human_identity
Revises: 003_project_api_keys
Create Date: 2026-07-18

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_human_identity"
down_revision: Union[str, None] = "003_project_api_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # WorkOS user subject (JWT `sub`), e.g. user_01H....
        sa.Column("workos_user_id", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("workos_user_id", name="uq_users_workos_user_id"),
    )

    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # WorkOS organization ID (JWT `org_id`), e.g. org_01H....
        sa.Column("workos_org_id", sa.String(length=64), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("workos_org_id", name="uq_organizations_workos_org_id"),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )

    # Nullable for safe migration; assignment happens via the admin CLI.
    op.add_column(
        "projects",
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_projects_organization_id", "projects", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_projects_organization_id", table_name="projects")
    op.drop_column("projects", "organization_id")
    op.drop_table("organizations")
    op.drop_table("users")
