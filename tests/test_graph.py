"""
Tests for GraphStore.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saurix.core.graph import SCHEMA_VERSION, GraphStore
from saurix.core.models import Edge, Symbol


class TestGraphStoreBasics:
    """
    Test basic GraphStore operations.
    """

    def test_add_symbol(self, empty_graph: GraphStore) -> None:
        """
        Test adding a symbol to the graph.
        """
        symbol = Symbol(
            id="python://test",
            type="module",
            language="python",
            name="test",
            file="test.py",
            line=1,
        )
        empty_graph.add_symbol(symbol)

        assert "python://test" in empty_graph.symbols
        assert empty_graph.symbols["python://test"].name == "test"

    def test_add_duplicate_symbol(self, empty_graph: GraphStore) -> None:
        """
        Test that duplicate symbols are not added.
        """
        symbol1 = Symbol(
            id="python://test",
            type="module",
            language="python",
            name="test",
            file="test.py",
            line=1,
        )
        symbol2 = Symbol(
            id="python://test",
            type="function",
            language="python",
            name="other",
            file="other.py",
            line=1,
        )

        empty_graph.add_symbol(symbol1)
        empty_graph.add_symbol(symbol2)

        assert len(empty_graph.symbols) == 1
        # First symbol should be kept
        assert empty_graph.symbols["python://test"].type == "module"

    def test_add_edge(self, empty_graph: GraphStore) -> None:
        """
        Test adding an edge to the graph.
        """
        edge = Edge(
            type="CALLS",
            source="python://a",
            target="python://b",
            language="python",
            confidence="high",
            file="test.py",
            line=10,
        )
        empty_graph.add_edge(edge)

        assert len(empty_graph.edges) == 1
        assert empty_graph.edges[0].type == "CALLS"

    def test_snapshot_and_contribution(self, empty_graph: GraphStore) -> None:
        """
        Test snapshot and contribution tracking.
        """
        # Take initial snapshot
        snapshot = empty_graph.snapshot_counts()
        assert snapshot == (0, 0)

        # Add symbols and edges
        symbol1 = Symbol(
            id="python://a",
            type="module",
            language="python",
            name="a",
            file="a.py",
            line=1,
        )
        symbol2 = Symbol(
            id="python://b",
            type="function",
            language="python",
            name="b",
            file="a.py",
            line=5,
        )
        empty_graph.add_symbol(symbol1)
        empty_graph.add_symbol(symbol2)
        empty_graph.add_edge(
            Edge(
                type="CONTAINS",
                source="python://a",
                target="python://b",
                language="python",
                confidence="high",
                file="a.py",
                line=5,
            )
        )

        # Get contribution since snapshot
        symbols, edges = empty_graph.contribution_since(snapshot)
        assert len(symbols) == 2
        assert len(edges) == 1


class TestGraphStoreStats:
    """
    Test GraphStore statistics.
    """

    def test_stats_empty_graph(self, empty_graph: GraphStore) -> None:
        """
        Test stats on empty graph.
        """
        stats = empty_graph.stats()

        assert stats["symbols"] == 0
        assert stats["edges"] == 0
        assert stats["symbol_types"] == {}
        assert stats["edge_types"] == {}
        assert stats["confidence_percentages"] == {}

    def test_stats_sample_graph(self, sample_graph: GraphStore) -> None:
        """
        Test stats on sample graph.
        """
        stats = sample_graph.stats()

        assert stats["symbols"] == 6
        assert stats["edges"] == 7

        # Check symbol types
        assert stats["symbol_types"]["module"] == 2
        assert stats["symbol_types"]["function"] == 2
        assert stats["symbol_types"]["class"] == 1
        assert stats["symbol_types"]["method"] == 1

        # Check edge types
        assert stats["edge_types"]["CONTAINS"] == 4
        assert stats["edge_types"]["CALLS"] == 2
        assert stats["edge_types"]["IMPORTS"] == 1

        # Check confidence
        assert stats["confidence_counts"]["high"] == 6
        assert stats["confidence_counts"]["medium"] == 1
        assert "high" in stats["confidence_percentages"]


class TestGraphStoreSerialization:
    """
    Test GraphStore serialization.
    """

    def test_to_dict(self, sample_graph: GraphStore) -> None:
        """
        Test converting graph to dict.
        """
        data = sample_graph.to_dict()

        assert data["schema_version"] == SCHEMA_VERSION
        assert len(data["symbols"]) == 6
        assert len(data["edges"]) == 7
        assert "metadata" in data

    def test_write_and_read_json(
        self, sample_graph: GraphStore, tmp_path: Path
    ) -> None:
        """
        Test writing and reading graph JSON.
        """
        graph_path = tmp_path / "test_graph.json"

        # Write
        sample_graph.write_json(graph_path)
        assert graph_path.exists()

        # Read
        loaded = GraphStore.from_json(graph_path)

        assert len(loaded.symbols) == 6
        assert len(loaded.edges) == 7
        assert "python://module1" in loaded.symbols

    def test_from_json_invalid_file(self, tmp_path: Path) -> None:
        """
        Test loading from non-existent file raises error.
        """
        with pytest.raises(FileNotFoundError):
            GraphStore.from_json(tmp_path / "nonexistent.json")

    def test_metadata_persistence(
        self, sample_graph: GraphStore, tmp_path: Path
    ) -> None:
        """
        Test that metadata survives serialization.
        """
        sample_graph.set_metadata("test_key", {"nested": "value"})
        sample_graph.set_metadata("extraction_coverage", {"python": {"files_seen": 10}})

        graph_path = tmp_path / "test_graph.json"
        sample_graph.write_json(graph_path)

        loaded = GraphStore.from_json(graph_path)
        assert loaded.metadata["test_key"] == {"nested": "value"}
        assert "extraction_coverage" in loaded.metadata


class TestGraphStoreEdgeCases:
    """
    Test edge cases and error handling.
    """

    def test_symbol_without_optional_fields(self, empty_graph: GraphStore) -> None:
        """
        Test symbols with minimal fields.
        """
        symbol = Symbol(
            id="minimal://test", type="symbol", language="unknown", name="test"
        )
        empty_graph.add_symbol(symbol)

        assert empty_graph.symbols["minimal://test"].file is None
        assert empty_graph.symbols["minimal://test"].line is None

    def test_edge_with_none_confidence(self, empty_graph: GraphStore) -> None:
        """
        Test edge with None confidence.
        """
        edge = Edge(
            type="CALLS",
            source="a",
            target="b",
            language="python",
            confidence=None,
            file="test.py",
            line=1,
        )
        empty_graph.add_edge(edge)

        stats = empty_graph.stats()
        assert stats["confidence_counts"]["unknown"] == 1
