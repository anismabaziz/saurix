"""
Graph Storage Module

This module defines the GraphStore class, which serves as the central data structure
for the Saurix knowledge graph. It manages symbols, edges, and their metadata,
providing efficient indexing for graph traversal and analysis.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import Edge, Symbol

# Bumped when the on-disk shape changes in a way a reader has to know about. 0.2.0
# wrote the key `nodes`, which 0.3.0 renamed to `symbols` alongside the model, so
# a graph written by an older Saurix is reported rather than silently half-read.
SCHEMA_VERSION = "2.0.0"


class GraphStore:
    """
    An in-memory graph storage engine with persistence capabilities.

    GraphStore maintains a collection of Symbols and Edges, and builds several
    lookup indexes on-the-fly to ensure that traversal operations (like finding
    all callers of a function) are O(1) or O(K) where K is the number of results.
    """

    def __init__(self) -> None:
        # Primary storage
        self._symbols: dict[str, Symbol] = {}
        self._edges: list[Edge] = []
        self._metadata: dict[str, object] = {}

        # Performance Indexes
        self._edges_by_source: dict[str, list[Edge]] = {}
        self._edges_by_target: dict[str, list[Edge]] = {}
        self._edges_by_type: dict[str, list[Edge]] = {}

        # Name index for symbols (one name may map to multiple IDs in different files)
        self._symbols_by_name: dict[str, list[str]] = {}

    @property
    def symbols(self) -> dict[str, Symbol]:
        """
        Returns the raw symbol mapping (ID -> Symbol).
        """
        return self._symbols

    @property
    def edges(self) -> list[Edge]:
        """
        Returns the list of all edges in the graph.
        """
        return self._edges

    def get_edges_from(self, symbol_id: str) -> list[Edge]:
        """
        Returns all edges where the given symbol_id is the source.
        """
        return self._edges_by_source.get(symbol_id, [])

    def get_edges_to(self, symbol_id: str) -> list[Edge]:
        """
        Returns all edges where the given symbol_id is the target.
        """
        return self._edges_by_target.get(symbol_id, [])

    def get_edges_by_type(self, edge_type: str) -> list[Edge]:
        """
        Returns all edges of a specific type (e.g., 'CALLS', 'IMPORTS').
        """
        return self._edges_by_type.get(edge_type, [])

    def get_symbols_by_name(self, name: str) -> list[Symbol]:
        """
        Returns all symbols matching a specific name string across all files.
        """
        ids = self._symbols_by_name.get(name, [])
        return [self._symbols[i] for i in ids if i in self._symbols]

    @property
    def metadata(self) -> dict[str, object]:
        """
        Returns the global metadata dictionary for this graph.
        """
        return self._metadata

    def add_symbol(self, symbol: Symbol) -> None:
        """
        Adds a symbol to the store and updates relevant indexes.
        """
        if symbol.id not in self._symbols:
            self._symbols[symbol.id] = symbol
            # Update the name-based index
            if symbol.name:
                if symbol.name not in self._symbols_by_name:
                    self._symbols_by_name[symbol.name] = []
                self._symbols_by_name[symbol.name].append(symbol.id)

    def add_edge(self, edge: Edge) -> None:
        """
        Adds an edge to the store and updates adjacency indexes.
        """
        self._edges.append(edge)

        # Update source index
        if edge.source not in self._edges_by_source:
            self._edges_by_source[edge.source] = []
        self._edges_by_source[edge.source].append(edge)

        # Update target index
        if edge.target not in self._edges_by_target:
            self._edges_by_target[edge.target] = []
        self._edges_by_target[edge.target].append(edge)

        # Update type index
        if edge.type not in self._edges_by_type:
            self._edges_by_type[edge.type] = []
        self._edges_by_type[edge.type].append(edge)

    def set_metadata(self, key: str, value: object) -> None:
        """
        Stores a piece of global metadata in the graph.
        """
        self._metadata[key] = value

    def stats(self) -> dict[str, object]:
        """
        Computes comprehensive statistics about the graph's contents.
        """
        symbol_types: dict[str, int] = {}
        edge_types: dict[str, int] = {}
        languages: dict[str, int] = {}
        confidence_counts: dict[str, int] = {}

        for symbol in self._symbols.values():
            symbol_types[symbol.type] = symbol_types.get(symbol.type, 0) + 1
            languages[symbol.language] = languages.get(symbol.language, 0) + 1

        for edge in self._edges:
            edge_types[edge.type] = edge_types.get(edge.type, 0) + 1
            confidence = edge.confidence or "unknown"
            confidence_counts[confidence] = confidence_counts.get(confidence, 0) + 1

        total_edges = len(self._edges)
        confidence_percentages = {
            key: round((value / total_edges) * 100, 2) if total_edges else 0.0
            for key, value in confidence_counts.items()
        }

        stats: dict[str, object] = {
            "symbols": len(self._symbols),
            "edges": len(self._edges),
            "symbol_types": symbol_types,
            "edge_types": edge_types,
            "languages": languages,
            "confidence_counts": confidence_counts,
            "confidence_percentages": confidence_percentages,
        }

        # Include optional metadata fields if present
        if "extraction_coverage" in self._metadata:
            stats["extraction_coverage"] = self._metadata["extraction_coverage"]

        return stats

    def to_dict(self) -> dict[str, object]:
        """
        Serializes the entire graph to a dictionary for JSON storage.
        """
        return {
            "schema_version": SCHEMA_VERSION,
            "metadata": self._metadata,
            "symbols": [asdict(symbol) for symbol in self._symbols.values()],
            "edges": [asdict(edge) for edge in self._edges],
        }

    def write_json(self, path: Path) -> None:
        """
        Writes the graph to a JSON file on disk.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, path: Path) -> GraphStore:
        """
        Loads a GraphStore from a JSON file.
        """
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        # Validate schema version to ensure backward compatibility
        schema_version = payload.get("schema_version", "unknown")
        if schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"Graph schema version mismatch: expected {SCHEMA_VERSION}, got "
                f"{schema_version}. Re-index the repository to rewrite the graph."
            )

        graph = cls()
        # Restore metadata
        for key, value in payload.get("metadata", {}).items():
            graph.set_metadata(key, value)

        # Restore symbols first (they are the atoms of the graph)
        for row in payload.get("symbols", []):
            graph.add_symbol(Symbol(**row))

        # Restore edges (indexes will be built as they are added)
        for row in payload.get("edges", []):
            graph.add_edge(Edge(**row))

        return graph
