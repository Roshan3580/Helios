"""project API keys for canonical v2 telemetry auth

Adds project_api_keys. Only a non-secret lookup prefix and a SHA-256 digest of
the complete key are stored; the plaintext key is never persisted. Scopes are
JSONB (no PostgreSQL enum) so new scope strings need no migration.

Legacy tables and the v1 path are untouched. Downgrade removes only this table.

Revision ID: 003_project_api_keys
Revises: 002_otel_foundation
Create Date: 2026-07-18

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_project_api_keys"
down_revision: Union[str, None] = "002_otel_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        # Non-secret lookup prefix; unique so a single row is found before the
        # constant-time hash comparison.
        sa.Column("key_prefix", sa.String(length=64), nullable=False),
        # SHA-256 hex digest of the complete plaintext key (never the secret alone).
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("key_prefix", name="uq_project_api_keys_prefix"),
    )
    op.create_index("ix_project_api_keys_project_id", "project_api_keys", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_project_api_keys_project_id", table_name="project_api_keys")
    op.drop_table("project_api_keys")
