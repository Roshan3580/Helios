"""Safe span hierarchy analysis for a single OTel trace detail.

Never mutates input span objects. Tolerates orphans, cycles, multiple roots,
empty traces, and defensive duplicate span IDs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class SpanNode:
    span_id: str
    parent_span_id: str | None
    name: str
    kind: int
    status_code: int
    status_message: str | None
    start_time: datetime
    end_time: datetime
    duration_ms: float
    attributes: Mapping[str, Any]
    scope_name: str | None
    is_root: bool
    is_orphan: bool


@dataclass
class TraceHierarchy:
    nodes: dict[str, SpanNode]
    roots: list[str]
    children: dict[str, list[str]]
    orphans: list[str]
    cycles: list[tuple[str, ...]]
    ordered_span_ids: list[str] = field(default_factory=list)


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    raise TypeError(f"unsupported datetime value: {type(value)!r}")


def _span_sort_key(node: SpanNode) -> tuple[datetime, str]:
    return (node.start_time, node.span_id)


def build_hierarchy(spans: Sequence[Mapping[str, Any]]) -> TraceHierarchy:
    """Build a parent→children graph from OTel span detail dicts."""
    # First pass: collect valid IDs for orphan detection.
    provisional: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw in spans:
        if not isinstance(raw, Mapping):
            continue
        span_id = raw.get("span_id")
        if not isinstance(span_id, str) or not span_id:
            continue
        if span_id in seen_ids:
            continue  # defensive: keep first occurrence
        seen_ids.add(span_id)
        provisional.append(dict(raw))

    known_ids = set(seen_ids)
    nodes: dict[str, SpanNode] = {}

    for raw in provisional:
        span_id = raw["span_id"]
        parent = raw.get("parent_span_id")
        if parent is not None and not isinstance(parent, str):
            parent = None
        if isinstance(parent, str) and not parent:
            parent = None
        try:
            start_time = _parse_datetime(raw.get("start_time"))
            end_time = _parse_datetime(raw.get("end_time"))
        except (TypeError, ValueError):
            continue
        try:
            duration_ms = float(raw.get("duration_ms", 0.0))
        except (TypeError, ValueError):
            duration_ms = 0.0
        if duration_ms != duration_ms or duration_ms < 0:
            duration_ms = 0.0

        attrs = raw.get("attributes")
        attrs = dict(attrs) if isinstance(attrs, dict) else {}

        status_message = raw.get("status_message")
        if status_message is not None and not isinstance(status_message, str):
            status_message = None
        name = raw.get("name") if isinstance(raw.get("name"), str) else ""
        try:
            kind_i = int(raw.get("kind", 0))
        except (TypeError, ValueError):
            kind_i = 0
        try:
            status_i = int(raw.get("status_code", 0))
        except (TypeError, ValueError):
            status_i = 0
        scope_name = raw.get("scope_name")
        if scope_name is not None and not isinstance(scope_name, str):
            scope_name = None

        is_orphan = parent is not None and parent not in known_ids
        is_root = parent is None

        nodes[span_id] = SpanNode(
            span_id=span_id,
            parent_span_id=parent,
            name=name,
            kind=kind_i,
            status_code=status_i,
            status_message=status_message,
            start_time=start_time,
            end_time=end_time,
            duration_ms=duration_ms,
            attributes=attrs,
            scope_name=scope_name,
            is_root=is_root,
            is_orphan=is_orphan,
        )

    children: dict[str, list[str]] = {span_id: [] for span_id in nodes}
    roots: list[str] = []
    orphans: list[str] = []
    for span_id, node in nodes.items():
        if node.is_orphan:
            orphans.append(span_id)
            continue
        if node.parent_span_id is None:
            roots.append(span_id)
            continue
        children[node.parent_span_id].append(span_id)

    for parent_id, child_ids in children.items():
        child_ids.sort(key=lambda cid: _span_sort_key(nodes[cid]))

    roots = sorted(roots, key=lambda sid: _span_sort_key(nodes[sid]))
    orphans = sorted(orphans, key=lambda sid: _span_sort_key(nodes[sid]))
    cycles = _detect_cycles(nodes)
    ordered = sorted(nodes.values(), key=_span_sort_key)
    return TraceHierarchy(
        nodes=nodes,
        roots=roots,
        children=children,
        orphans=orphans,
        cycles=cycles,
        ordered_span_ids=[n.span_id for n in ordered],
    )


def _detect_cycles(nodes: dict[str, SpanNode]) -> list[tuple[str, ...]]:
    """Return deterministic, deduplicated cycles as span-id tuples."""
    parent_of = {
        sid: node.parent_span_id
        for sid, node in nodes.items()
        if node.parent_span_id and node.parent_span_id in nodes
    }
    cycles: list[tuple[str, ...]] = []
    seen_cycle_keys: set[tuple[str, ...]] = set()

    for start in sorted(nodes.keys()):
        path: list[str] = []
        index: dict[str, int] = {}
        current: str | None = start
        while current is not None:
            if current in index:
                cycle = path[index[current] :]
                min_id = min(cycle)
                rot = cycle.index(min_id)
                rotated = tuple(cycle[rot:] + cycle[:rot])
                if rotated not in seen_cycle_keys:
                    seen_cycle_keys.add(rotated)
                    cycles.append(rotated)
                break
            index[current] = len(path)
            path.append(current)
            nxt = parent_of.get(current)
            if nxt is None:
                break
            current = nxt
            if len(path) > len(nodes) + 1:
                break

    cycles.sort(key=lambda c: (len(c), c))
    return cycles
