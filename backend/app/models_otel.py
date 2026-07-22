"""Canonical v2 OpenTelemetry trace-storage models.

Kept separate from the legacy models in app/models.py: the legacy Trace/Span
tables remain untouched for /v1 compatibility while these tables back the
canonical OTLP ingestion path and /v2 read APIs.

OTel span kind and status code are stored as integer wire values (validated
at the application layer) rather than PostgreSQL enums, so new OTel values
never require a migration.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models import Project

# OTel wire values (kept as plain ints in storage).
SPAN_KIND_VALUES = frozenset(range(0, 6))  # UNSPECIFIED..CONSUMER
STATUS_CODE_VALUES = frozenset((0, 1, 2))  # UNSET, OK, ERROR
STATUS_CODE_ERROR = 2


class OtelTrace(Base):
    __tablename__ = "otel_traces"
    __table_args__ = (
        UniqueConstraint("project_id", "trace_id", name="uq_otel_traces_project_trace"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=False)
    trace_id: Mapped[str] = mapped_column(String(32))
    service_name: Mapped[str] = mapped_column(String(255))
    environment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    root_span_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    root_span_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    span_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped[Project] = relationship()
    spans: Mapped[list["OtelSpan"]] = relationship(
        back_populates="trace",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="OtelSpan.start_time",
    )


class OtelSpan(Base):
    __tablename__ = "otel_spans"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "trace_id", "span_id", name="uq_otel_spans_project_trace_span"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    otel_trace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("otel_traces.id", ondelete="CASCADE")
    )
    trace_id: Mapped[str] = mapped_column(String(32))
    span_id: Mapped[str] = mapped_column(String(16))
    parent_span_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    name: Mapped[str] = mapped_column(String(512))
    kind: Mapped[int] = mapped_column(SmallInteger, default=0)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_ns: Mapped[int] = mapped_column(BigInteger)
    status_code: Mapped[int] = mapped_column(SmallInteger, default=0)
    status_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_flags: Mapped[int] = mapped_column(Integer, default=0)
    resource_attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    scope_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scope_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scope_attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    events: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    links: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    dropped_attributes_count: Mapped[int] = mapped_column(Integer, default=0)
    dropped_events_count: Mapped[int] = mapped_column(Integer, default=0)
    dropped_links_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped[Project] = relationship()
    trace: Mapped[OtelTrace] = relationship(back_populates="spans")
