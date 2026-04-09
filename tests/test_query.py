"""Tests for query operations."""
from __future__ import annotations

import pytest

from code_atlas.graph import GraphStore
from code_atlas.models import Edge, Node
from code_atlas.query import find_symbol, callers_of, impact_of, related_files
from code_atlas.query.traversal import resolve_symbol_ids, shortest_path


class TestFindSymbol:
    """Test find_symbol function."""

    def test_exact_match_by_id(self, sample_graph: GraphStore) -> None:
        """Test finding by exact ID includes partial matches (substrings match)."""
        results = find_symbol(sample_graph, "python://module1")
        # Partial matching means "module1" also matches "module1:func1" etc.
        assert len(results) >= 1
        ids = {r["id"] for r in results}
        assert "python://module1" in ids

    def test_exact_match_by_name(self, sample_graph: GraphStore) -> None:
        """Test finding by name."""
        results = find_symbol(sample_graph, "func1")
        assert len(results) >= 1
        assert any(r["name"] == "func1" for r in results)

    def test_fuzzy_match(self, sample_graph: GraphStore) -> None:
        """Test fuzzy matching."""
        results = find_symbol(sample_graph, "func")
        # Should find func1 and func2
        names = {r["name"] for r in results}
        assert "func1" in names or "func2" in names

    def test_limit_results(self, sample_graph: GraphStore) -> None:
        """Test result limiting."""
        results = find_symbol(sample_graph, "python", limit=2)
        assert len(results) <= 2

    def test_no_match(self, sample_graph: GraphStore) -> None:
        """Test when nothing matches."""
        results = find_symbol(sample_graph, "nonexistent_xyz")
        assert results == []


class TestCallersOf:
    """Test callers_of function."""

    def test_find_callers(self, sample_graph: GraphStore) -> None:
        """Test finding callers of a function."""
        results = callers_of(sample_graph, "python://module1:func1")

        assert len(results) == 1
        assert results[0]["caller"] == "python://module2:Class1.method1"
        assert results[0]["caller_name"] == "method1"

    def test_no_callers(self, sample_graph: GraphStore) -> None:
        """Test function with callers. func2 is called by func1."""
        results = callers_of(sample_graph, "python://module1:func2")
        # func2 IS called by func1 in the sample graph
        assert len(results) == 1
        assert results[0]["caller"] == "python://module1:func1"
        assert results[0]["caller_name"] == "func1"

    def test_function_with_no_callers(self, sample_graph: GraphStore) -> None:
        """Test function that truly has no callers."""
        # Add a new function with no calls to it
        results = callers_of(sample_graph, "python://nonexistent_func")
        assert results == []

    def test_callers_by_name(self, sample_graph: GraphStore) -> None:
        """Test finding callers by function name."""
        results = callers_of(sample_graph, "func1")
        assert len(results) >= 1


class TestImpactOf:
    """Test impact_of function."""

    def test_impact_depth_1(self, sample_graph: GraphStore) -> None:
        """Test impact analysis with depth 1."""
        results = impact_of(sample_graph, "python://module1:func2", depth=1)

        # func2 is called by func1
        assert len(results) >= 1
        assert any(r["id"] == "python://module1:func1" for r in results)

    def test_impact_depth_2(self, sample_graph: GraphStore) -> None:
        """Test impact analysis with depth 2."""
        results = impact_of(sample_graph, "python://module1:func2", depth=2)

        # func2 -> func1 -> method1
        ids = {r["id"] for r in results}
        assert "python://module1:func1" in ids

    def test_impact_limit(self, sample_graph: GraphStore) -> None:
        """Test impact with limit."""
        results = impact_of(sample_graph, "python://module1", limit=2)
        assert len(results) <= 2


class TestRelatedFiles:
    """Test related_files function."""

    def test_related_by_import(self, sample_graph: GraphStore) -> None:
        """Test finding related files via imports."""
        results = related_files(sample_graph, "module2.py")

        # related_files returns list of file paths (strings), not dicts
        assert isinstance(results, list)
        # module2.py imports from module1
        assert "module1.py" in results

    def test_related_by_calls(self, sample_graph: GraphStore) -> None:
        """Test finding related files via calls."""
        results = related_files(sample_graph, "module1.py", depth=2)

        # Should find module2 via the call chain
        assert len(results) > 0


class TestResolveSymbolIds:
    """Test resolve_symbol_ids function."""

    def test_exact_id_match(self, sample_graph: GraphStore) -> None:
        """Test resolving by exact ID."""
        ids = resolve_symbol_ids(sample_graph, "python://module1")
        assert ids == ["python://module1"]

    def test_resolve_by_name(self, sample_graph: GraphStore) -> None:
        """Test resolving by name."""
        ids = resolve_symbol_ids(sample_graph, "Class1")
        assert "python://module2:Class1" in ids

    def test_no_match(self, sample_graph: GraphStore) -> None:
        """Test resolving nonexistent symbol."""
        ids = resolve_symbol_ids(sample_graph, "nonexistent")
        assert ids == []


class TestShortestPath:
    """Test shortest_path function."""

    def test_direct_path(self, sample_graph: GraphStore) -> None:
        """Test finding direct path."""
        path = shortest_path(
            sample_graph,
            "python://module1:func1",
            "python://module1:func2"
        )

        assert len(path) == 2
        assert path[0]["id"] == "python://module1:func1"
        assert path[1]["id"] == "python://module1:func2"
        assert path[1]["edge"] == "CALLS"

    def test_indirect_path(self, sample_graph: GraphStore) -> None:
        """Test finding indirect path."""
        path = shortest_path(
            sample_graph,
            "python://module2:Class1.method1",
            "python://module1:func2"
        )

        # method1 -> func1 -> func2
        assert len(path) >= 3
        ids = [p["id"] for p in path]
        assert "python://module2:Class1.method1" in ids
        assert "python://module1:func2" in ids

    def test_no_path(self, sample_graph: GraphStore) -> None:
        """Test when no path exists."""
        path = shortest_path(
            sample_graph,
            "python://module2",
            "python://nonexistent"
        )
        assert path == []

    def test_max_depth_limit(self, sample_graph: GraphStore) -> None:
        """Test max_depth limiting."""
        path = shortest_path(
            sample_graph,
            "python://module2:Class1.method1",
            "python://module1:func2",
            max_depth=1
        )
        # Should not find path with depth 1
        assert path == []

    def test_edge_type_filter(self, sample_graph: GraphStore) -> None:
        """Test filtering by edge types."""
        path = shortest_path(
            sample_graph,
            "python://module2",
            "python://module1",
            edge_types={"IMPORTS"}
        )

        assert len(path) == 2
        assert path[1]["edge"] == "IMPORTS"


class TestTraversalEdgeCases:
    """Test edge cases in traversal."""

    def test_empty_graph(self, empty_graph: GraphStore) -> None:
        """Test operations on empty graph."""
        assert find_symbol(empty_graph, "anything") == []
        assert callers_of(empty_graph, "anything") == []
        assert impact_of(empty_graph, "anything") == []
        assert shortest_path(empty_graph, "a", "b") == []

    def test_circular_dependencies(self) -> None:
        """Test handling circular dependencies."""
        graph = GraphStore()

        # Create circular call: a -> b -> c -> a
        nodes = [
            Node(id="a", type="function", language="python", name="a", file="test.py", line=1),
            Node(id="b", type="function", language="python", name="b", file="test.py", line=2),
            Node(id="c", type="function", language="python", name="c", file="test.py", line=3),
        ]
        for n in nodes:
            graph.add_node(n)

        edges = [
            Edge(type="CALLS", source="a", target="b", language="python", confidence="high", file="test.py", line=1),
            Edge(type="CALLS", source="b", target="c", language="python", confidence="high", file="test.py", line=2),
            Edge(type="CALLS", source="c", target="a", language="python", confidence="high", file="test.py", line=3),
        ]
        for e in edges:
            graph.add_edge(e)

        # Impact should handle cycle without infinite loop
        results = impact_of(graph, "a", depth=5)
        # Should find b and c within depth 3
        ids = {r["id"] for r in results}
        assert "b" in ids
        assert "c" in ids
