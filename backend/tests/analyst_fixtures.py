"""Deterministic in-memory OTel trace-detail fixtures for analyst tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

PROJECT_ID = UUID("11111111-1111-1111-1111-111111111111")
TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
BASE = datetime(2026, 7, 18, 18, 0, 0, tzinfo=timezone.utc)


def span(
    span_id: str,
    *,
    name: str = "span",
    parent_span_id: str | None = None,
    start_offset_ms: float = 0.0,
    duration_ms: float = 10.0,
    status_code: int = 0,
    status_message: str | None = None,
    attributes: dict[str, Any] | None = None,
    kind: int = 1,
    scope_name: str | None = "helios.tests",
) -> dict[str, Any]:
    start = BASE + timedelta(milliseconds=start_offset_ms)
    end = start + timedelta(milliseconds=duration_ms)
    return {
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "name": name,
        "kind": kind,
        "status_code": status_code,
        "status_message": status_message,
        "start_time": start,
        "end_time": end,
        "duration_ms": duration_ms,
        "trace_state": None,
        "trace_flags": 0,
        "resource_attributes": {"service.name": "test-service"},
        "scope_name": scope_name,
        "scope_version": "0.0.1",
        "scope_attributes": {},
        "attributes": dict(attributes or {}),
        "events": [],
        "links": [],
        "dropped_attributes_count": 0,
        "dropped_events_count": 0,
        "dropped_links_count": 0,
    }


def trace_detail(
    spans: list[dict[str, Any]],
    *,
    trace_id: str = TRACE_ID,
    duration_ms: float | None = None,
    root_span_id: str | None = None,
) -> dict[str, Any]:
    if spans:
        start = min(s["start_time"] for s in spans)
        end = max(s["end_time"] for s in spans)
        computed = (end - start).total_seconds() * 1000.0
    else:
        start = BASE
        end = BASE
        computed = 0.0
    roots = [s for s in spans if s.get("parent_span_id") is None]
    root = roots[0] if roots else None
    return {
        "trace_id": trace_id,
        "project_slug": "analyst-proj",
        "service_name": "test-service",
        "environment": "test",
        "start_time": start,
        "end_time": end,
        "duration_ms": computed if duration_ms is None else duration_ms,
        "root_span_id": root_span_id
        if root_span_id is not None
        else (root["span_id"] if root else None),
        "root_span_name": root["name"] if root else None,
        "span_count": len(spans),
        "error_count": sum(1 for s in spans if s.get("status_code") == 2),
        "first_seen_at": start,
        "last_seen_at": end,
        "spans": spans,
    }
