import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TraceStatus(str, enum.Enum):
    success = "success"
    warning = "warning"
    error = "error"


class SpanType(str, enum.Enum):
    input = "input"
    rag = "rag"
    llm = "llm"
    tool = "tool"
    output = "output"
    evaluator = "evaluator"


class SpanStatus(str, enum.Enum):
    success = "success"
    warning = "warning"
    error = "error"


class RagChunkStatus(str, enum.Enum):
    ok = "ok"
    drift = "drift"
    low = "low"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    environment: Mapped[str] = mapped_column(String(64), default="production")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    traces: Mapped[list["Trace"]] = relationship(back_populates="project")
    prompt_versions: Mapped[list["PromptVersion"]] = relationship(back_populates="project")
    evaluation_runs: Mapped[list["EvaluationRun"]] = relationship(back_populates="project")
    rag_chunk_metrics: Mapped[list["RagChunkMetric"]] = relationship(back_populates="project")


class Trace(Base):
    __tablename__ = "traces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    trace_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_query: Mapped[str] = mapped_column(Text)
    app_name: Mapped[str] = mapped_column(String(255))
    model: Mapped[str] = mapped_column(String(128))
    status: Mapped[TraceStatus] = mapped_column(Enum(TraceStatus, name="trace_status"))
    latency_ms: Mapped[int] = mapped_column(Integer)
    total_tokens: Mapped[int] = mapped_column(Integer)
    prompt_tokens: Mapped[int] = mapped_column(Integer)
    completion_tokens: Mapped[int] = mapped_column(Integer)
    estimated_cost_usd: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="traces")
    spans: Mapped[list["Span"]] = relationship(back_populates="trace", cascade="all, delete-orphan")


class Span(Base):
    __tablename__ = "spans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("traces.id"), index=True)
    span_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    parent_span_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    span_type: Mapped[SpanType] = mapped_column(Enum(SpanType, name="span_type"))
    provider: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[SpanStatus] = mapped_column(Enum(SpanStatus, name="span_status"))
    input_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    trace: Mapped["Trace"] = relationship(back_populates="spans")


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    eval_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="prompt_versions")


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    dataset_name: Mapped[str] = mapped_column(String(255))
    prompt_name: Mapped[str] = mapped_column(String(255))
    model: Mapped[str] = mapped_column(String(128))
    accuracy: Mapped[float] = mapped_column(Float)
    citation_coverage: Mapped[float] = mapped_column(Float)
    latency_ms: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="evaluation_runs")


class RagChunkMetric(Base):
    __tablename__ = "rag_chunk_metrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    chunk_ref: Mapped[str] = mapped_column(String(255))
    retrieval_hits: Mapped[int] = mapped_column(Integer)
    quality_score: Mapped[float] = mapped_column(Float)
    status: Mapped[RagChunkStatus] = mapped_column(Enum(RagChunkStatus, name="rag_chunk_status"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="rag_chunk_metrics")
