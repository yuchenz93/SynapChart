"""Tests for DAG resolution (core.graph)."""

from __future__ import annotations

import pytest

from core.graph import (
    all_descendants,
    build_downstream_map,
    build_upstream_map,
    topological_sort,
)


def _nodes(*ids):
    return [{"node_id": i} for i in ids]


def _edge(src, tgt):
    return {"source_node_id": src, "target_node_id": tgt}


class TestTopologicalSort:
    def test_linear_chain_orders_source_first(self):
        nodes = _nodes("a", "b", "c")
        edges = [_edge("a", "b"), _edge("b", "c")]
        assert topological_sort(nodes, edges) == ["a", "b", "c"]

    def test_respects_partial_order_in_diamond(self):
        # a -> b, a -> c, b -> d, c -> d
        nodes = _nodes("a", "b", "c", "d")
        edges = [_edge("a", "b"), _edge("a", "c"), _edge("b", "d"), _edge("c", "d")]
        order = topological_sort(nodes, edges)
        assert order.index("a") < order.index("b")
        assert order.index("a") < order.index("c")
        assert order.index("b") < order.index("d")
        assert order.index("c") < order.index("d")

    def test_isolated_nodes_are_included(self):
        nodes = _nodes("a", "b", "lonely")
        edges = [_edge("a", "b")]
        assert set(topological_sort(nodes, edges)) == {"a", "b", "lonely"}

    def test_cycle_raises_valueerror(self):
        nodes = _nodes("a", "b", "c")
        edges = [_edge("a", "b"), _edge("b", "c"), _edge("c", "a")]
        with pytest.raises(ValueError, match="cycle"):
            topological_sort(nodes, edges)

    def test_self_loop_raises(self):
        nodes = _nodes("a")
        edges = [_edge("a", "a")]
        with pytest.raises(ValueError, match="cycle"):
            topological_sort(nodes, edges)

    def test_empty_graph(self):
        assert topological_sort([], []) == []


class TestAdjacencyMaps:
    def test_upstream_map(self):
        edges = [_edge("a", "c"), _edge("b", "c")]
        up = build_upstream_map(edges)
        assert sorted(up["c"]) == ["a", "b"]
        assert "a" not in up  # sources have no upstream entry

    def test_downstream_map(self):
        edges = [_edge("a", "b"), _edge("a", "c")]
        down = build_downstream_map(edges)
        assert sorted(down["a"]) == ["b", "c"]


class TestDescendants:
    def test_transitive_descendants(self):
        # a -> b -> c -> d, plus a -> e
        edges = [_edge("a", "b"), _edge("b", "c"), _edge("c", "d"), _edge("a", "e")]
        down = build_downstream_map(edges)
        assert all_descendants("a", down) == {"b", "c", "d", "e"}
        assert all_descendants("b", down) == {"c", "d"}

    def test_leaf_has_no_descendants(self):
        edges = [_edge("a", "b")]
        down = build_downstream_map(edges)
        assert all_descendants("b", down) == set()

    def test_descendants_handles_diamond_without_double_visit(self):
        # a -> b, a -> c, b -> d, c -> d  (d reachable two ways)
        edges = [_edge("a", "b"), _edge("a", "c"), _edge("b", "d"), _edge("c", "d")]
        down = build_downstream_map(edges)
        assert all_descendants("a", down) == {"b", "c", "d"}
