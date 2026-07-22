"""Hierarchy builder tests for the analyst engine."""

from copy import deepcopy

from app.analyst.hierarchy import build_hierarchy
from analyst_fixtures import span


class TestHierarchy:
    def test_normal_tree_and_child_order(self):
        spans = [
            span("root", name="root", duration_ms=100),
            span(
                "b",
                name="b",
                parent_span_id="root",
                start_offset_ms=20,
                duration_ms=10,
            ),
            span(
                "a",
                name="a",
                parent_span_id="root",
                start_offset_ms=10,
                duration_ms=10,
            ),
        ]
        original = deepcopy(spans)
        h = build_hierarchy(spans)
        assert h.roots == ["root"]
        assert h.children["root"] == ["a", "b"]  # start time then id
        assert spans == original  # no mutation

    def test_multiple_roots(self):
        spans = [
            span("r1", name="r1", start_offset_ms=0),
            span("r2", name="r2", start_offset_ms=5),
        ]
        h = build_hierarchy(spans)
        assert h.roots == ["r1", "r2"]

    def test_orphan(self):
        spans = [
            span("root", name="root"),
            span("kid", name="kid", parent_span_id="missing", start_offset_ms=1),
        ]
        h = build_hierarchy(spans)
        assert h.orphans == ["kid"]
        assert "kid" not in h.roots
        assert h.nodes["kid"].is_orphan

    def test_cycle_dedup(self):
        # a -> b -> a
        spans = [
            span("a", name="a", parent_span_id="b", start_offset_ms=0),
            span("b", name="b", parent_span_id="a", start_offset_ms=1),
        ]
        h = build_hierarchy(spans)
        assert len(h.cycles) == 1
        assert set(h.cycles[0]) == {"a", "b"}
        # Canonical rotation starts at lexicographically smallest.
        assert h.cycles[0][0] == "a"

    def test_empty_and_deep(self):
        assert build_hierarchy([]).ordered_span_ids == []
        spans = [span("n0", name="n0")]
        for i in range(1, 8):
            spans.append(
                span(
                    f"n{i}",
                    name=f"n{i}",
                    parent_span_id=f"n{i-1}",
                    start_offset_ms=i,
                    duration_ms=1,
                )
            )
        h = build_hierarchy(spans)
        assert h.roots == ["n0"]
        assert h.children["n6"] == ["n7"]
        assert not h.cycles

    def test_duplicate_span_id_keeps_first(self):
        spans = [
            span("dup", name="first", duration_ms=5),
            span("dup", name="second", duration_ms=9),
        ]
        h = build_hierarchy(spans)
        assert h.nodes["dup"].name == "first"
