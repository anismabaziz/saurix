from __future__ import annotations

"""
Graph Storage Module

This module defines the GraphStore class, which serves as the central data structure
for the Code Atlas knowledge graph. It manages nodes, edges, and their metadata,
providing efficient indexing for graph traversal and analysis.
"""

import json
from dataclasses import asdict
from pathlib import Path

from .models import Edge, Node


class GraphStore:
    """
    An in-memory graph storage engine with persistence capabilities.
    
    GraphStore maintains a collection of Nodes and Edges, and builds several
    lookup indexes on-the-fly to ensure that traversal operations (like finding
    all callers of a function) are O(1) or O(K) where K is the number of results.
    """
    def __init__(self) -> None:
        # Primary storage
        self._nodes: dict[str, Node] = {}
        self._edges: list[Edge] = []
        self._metadata: dict[str, object] = {}
        
        # Performance Indexes
        self._edges_by_source: dict[str, list[Edge]] = {}
        self._edges_by_target: dict[str, list[Edge]] = {}
        self._edges_by_type: dict[str, list[Edge]] = {}
        
        # Name index for nodes (one name may map to multiple IDs in different files)
        self._nodes_by_name: dict[str, list[str]] = {}

    @property
    def nodes(self) -> dict[str, Node]:
        """Returns the raw node mapping (ID -> Node)."""
        return self._nodes

    @property
    def edges(self) -> list[Edge]:
        """Returns the list of all edges in the graph."""
        return self._edges

    def get_edges_from(self, node_id: str) -> list[Edge]:
        """Returns all edges where the given node_id is the source."""
        return self._edges_by_source.get(node_id, [])

    def get_edges_to(self, node_id: str) -> list[Edge]:
        """Returns all edges where the given node_id is the target."""
        return self._edges_by_target.get(node_id, [])

    def get_edges_by_type(self, edge_type: str) -> list[Edge]:
        """Returns all edges of a specific type (e.g., 'CALLS', 'IMPORTS')."""
        return self._edges_by_type.get(edge_type, [])

    def get_nodes_by_name(self, name: str) -> list[Node]:
        """Returns all nodes matching a specific name string across all files."""
        ids = self._nodes_by_name.get(name, [])
        return [self._nodes[i] for i in ids if i in self._nodes]

    @property
    def metadata(self) -> dict[str, object]:
        """Returns the global metadata dictionary for this graph."""
        return self._metadata

    def add_node(self, node: Node) -> None:
        """Adds a node to the store and updates relevant indexes."""
        if node.id not in self._nodes:
            self._nodes[node.id] = node
            # Update the name-based index
            if node.name:
                if node.name not in self._nodes_by_name:
                    self._nodes_by_name[node.name] = []
                self._nodes_by_name[node.name].append(node.id)

    def add_edge(self, edge: Edge) -> None:
        """Adds an edge to the store and updates adjacency indexes."""
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

    def snapshot_counts(self) -> tuple[int, int]:
        """Returns a snapshot of current node/edge counts (used for delta tracking)."""
        return len(self._nodes), len(self._edges)

    def contribution_since(self, start: tuple[int, int]) -> tuple[list[Node], list[Edge]]:
        """Returns the nodes and edges added to the store since the given snapshot."""
        start_nodes, start_edges = start
        nodes = list(self._nodes.values())[start_nodes:]
        edges = self._edges[start_edges:]
        return nodes, edges

    def set_metadata(self, key: str, value: object) -> None:
        """Stores a piece of global metadata in the graph."""
        self._metadata[key] = value

    def stats(self) -> dict[str, object]:
        """Computes comprehensive statistics about the graph's contents."""
        node_types: dict[str, int] = {}
        edge_types: dict[str, int] = {}
        languages: dict[str, int] = {}
        confidence_counts: dict[str, int] = {}

        for node in self._nodes.values():
            node_types[node.type] = node_types.get(node.type, 0) + 1
            languages[node.language] = languages.get(node.language, 0) + 1

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
            "nodes": len(self._nodes),
            "edges": len(self._edges),
            "node_types": node_types,
            "edge_types": edge_types,
            "languages": languages,
            "confidence_counts": confidence_counts,
            "confidence_percentages": confidence_percentages,
        }
        
        # Include optional metadata fields if present
        if "extraction_coverage" in self._metadata:
            stats["extraction_coverage"] = self._metadata["extraction_coverage"]
        if "incremental_cache" in self._metadata:
            stats["incremental_cache"] = self._metadata["incremental_cache"]
            
        return stats

    def to_dict(self) -> dict[str, object]:
        """Serializes the entire graph to a dictionary for JSON storage."""
        return {
            "schema_version": "1.0.0",
            "metadata": self._metadata,
            "nodes": [asdict(node) for node in self._nodes.values()],
            "edges": [asdict(edge) for edge in self._edges],
        }

    def write_json(self, path: Path) -> None:
        """Writes the graph to a JSON file on disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, path: Path) -> "GraphStore":
        """Loads a GraphStore from a JSON file."""
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        # Validate schema version to ensure backward compatibility
        schema_version = payload.get("schema_version", "unknown")
        if schema_version != "1.0.0":
            import warnings
            warnings.warn(f"Graph schema version mismatch: expected 1.0.0, got {schema_version}", UserWarning)

        graph = cls()
        # Restore metadata
        for key, value in payload.get("metadata", {}).items():
            graph.set_metadata(key, value)

        # Restore nodes first (they are the atoms of the graph)
        for row in payload.get("nodes", []):
            graph.add_node(Node(**row))

        # Restore edges (indexes will be built as they are added)
        for row in payload.get("edges", []):
            graph.add_edge(Edge(**row))

        return graph
