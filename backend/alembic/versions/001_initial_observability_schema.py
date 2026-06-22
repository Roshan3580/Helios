"""initial observability schema

Revision ID: 001_initial
Revises:
Create Date: 2026-06-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

trace_status = postgresql.ENUM("success", "warning", "error", name="trace_status", create_type=False)
span_type = postgresql.ENUM(
    "input", "rag", "llm", "tool", "output", "evaluator", name="span_type", create_type=False
)
span_status = postgresql.ENUM("success", "warning", "error", name="span_status", create_type=False)
rag_chunk_status = postgresql.ENUM("ok", "drift", "low", name="rag_chunk_status", create_type=False)


def upgrade() -> None:
    op.execute("CREATE TYPE trace_status AS ENUM ('success', 'warning', 'error')")
    op.execute(
        "CREATE TYPE span_type AS ENUM ('input', 'rag', 'llm', 'tool', 'output', 'evaluator')"
    )
    op.execute("CREATE TYPE span_status AS ENUM ('success', 'warning', 'error')")
    op.execute("CREATE TYPE rag_chunk_status AS ENUM ('ok', 'drift', 'low')")

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_projects_slug", "projects", ["slug"], unique=True)

    op.create_table(
        "traces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("user_query", sa.Text(), nullable=False),
        sa.Column("app_name", sa.String(length=255), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("status", trace_status, nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_traces_project_id", "traces", ["project_id"])
    op.create_index("ix_traces_trace_id", "traces", ["trace_id"], unique=True)

    op.create_table(
        "spans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("traces.id"), nullable=False),
        sa.Column("span_id", sa.String(length=64), nullable=False),
        sa.Column("parent_span_id", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("span_type", span_type, nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("status", span_status, nullable=False),
        sa.Column("input_preview", sa.Text(), nullable=True),
        sa.Column("output_preview", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_spans_trace_id", "spans", ["trace_id"])
    op.create_index("ix_spans_span_id", "spans", ["span_id"], unique=True)
    op.create_index("ix_spans_parent_span_id", "spans", ["parent_span_id"])

    op.create_table(
        "prompt_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("eval_score", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_prompt_versions_project_id", "prompt_versions", ["project_id"])

    op.create_table(
        "evaluation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("dataset_name", sa.String(length=255), nullable=False),
        sa.Column("prompt_name", sa.String(length=255), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("accuracy", sa.Float(), nullable=False),
        sa.Column("citation_coverage", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_evaluation_runs_project_id", "evaluation_runs", ["project_id"])

    op.create_table(
        "rag_chunk_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("chunk_ref", sa.String(length=255), nullable=False),
        sa.Column("retrieval_hits", sa.Integer(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("status", rag_chunk_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_rag_chunk_metrics_project_id", "rag_chunk_metrics", ["project_id"])


def downgrade() -> None:
    op.drop_table("rag_chunk_metrics")
    op.drop_table("evaluation_runs")
    op.drop_table("prompt_versions")
    op.drop_table("spans")
    op.drop_table("traces")
    op.drop_table("projects")
    op.execute("DROP TYPE rag_chunk_status")
    op.execute("DROP TYPE span_status")
    op.execute("DROP TYPE span_type")
    op.execute("DROP TYPE trace_status")
