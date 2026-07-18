"""canonical OpenTelemetry trace storage (v2)

Adds otel_traces and otel_spans alongside the legacy traces/spans tables.
Legacy tables are untouched; downgrade removes only the new v2 objects.

No PostgreSQL enums: OTel span kind and status code are stored as integer
wire values, validated in the application layer, so new values never
require a migration.

Revision ID: 002_otel_foundation
Revises: 001_initial
Create Date: 2026-07-18

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_otel_foundation"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "otel_traces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        # 32 lowercase hex chars (16-byte W3C trace ID)
        sa.Column("trace_id", sa.String(length=32), nullable=False),
        sa.Column("service_name", sa.String(length=255), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        # Earliest span start / latest span end, recomputed from stored spans
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        # 16 lowercase hex chars (8-byte span ID); null until a root span arrives
        sa.Column("root_span_id", sa.String(length=16), nullable=True),
        sa.Column("root_span_name", sa.String(length=512), nullable=True),
        sa.Column("span_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
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
        sa.UniqueConstraint("project_id", "trace_id", name="uq_otel_traces_project_trace"),
    )
    op.create_index(
        "ix_otel_traces_project_start",
        "otel_traces",
        ["project_id", sa.text("start_time DESC")],
    )

    op.create_table(
        "otel_spans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column(
            "otel_trace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("otel_traces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trace_id", sa.String(length=32), nullable=False),
        sa.Column("span_id", sa.String(length=16), nullable=False),
        sa.Column("parent_span_id", sa.String(length=16), nullable=True),
        sa.Column("name", sa.String(length=512), nullable=False),
        # OTel SpanKind wire value (0=UNSPECIFIED..5=CONSUMER); int, not enum
        sa.Column("kind", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ns", sa.BigInteger(), nullable=False),
        # OTel StatusCode wire value (0=UNSET, 1=OK, 2=ERROR); int, not enum
        sa.Column("status_code", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column("trace_state", sa.Text(), nullable=True),
        sa.Column("trace_flags", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "resource_attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("scope_name", sa.String(length=255), nullable=True),
        sa.Column("scope_version", sa.String(length=64), nullable=True),
        sa.Column(
            "scope_attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "events",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "links",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "dropped_attributes_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("dropped_events_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dropped_links_count", sa.Integer(), nullable=False, server_default="0"),
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
        # Span identity is scoped to project + trace, never globally unique.
        sa.UniqueConstraint(
            "project_id", "trace_id", "span_id", name="uq_otel_spans_project_trace_span"
        ),
    )
    op.create_index("ix_otel_spans_trace_start", "otel_spans", ["otel_trace_id", "start_time"])
    op.create_index(
        "ix_otel_spans_project_start",
        "otel_spans",
        ["project_id", sa.text("start_time DESC")],
    )
    op.create_index(
        "ix_otel_spans_trace_parent", "otel_spans", ["otel_trace_id", "parent_span_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_otel_spans_trace_parent", table_name="otel_spans")
    op.drop_index("ix_otel_spans_project_start", table_name="otel_spans")
    op.drop_index("ix_otel_spans_trace_start", table_name="otel_spans")
    op.drop_table("otel_spans")
    op.drop_index("ix_otel_traces_project_start", table_name="otel_traces")
    op.drop_table("otel_traces")
