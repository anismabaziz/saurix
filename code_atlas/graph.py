from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import Edge, Node


class GraphStore:
    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._edges: list[Edge] = []

    @property
    def nodes(self) -> dict[str, Node]:
        return self._nodes

    @property
    def edges(self) -> list[Edge]:
        return self._edges

    def add_node(self, node: Node) -> None:
        if node.id not in self._nodes:
            self._nodes[node.id] = node

    def add_edge(self, edge: Edge) -> None:
        self._edges.append(edge)

    def stats(self) -> dict[str, object]:
        node_types: dict[str, int] = {}
        edge_types: dict[str, int] = {}
        languages: dict[str, int] = {}

        for node in self._nodes.values():
            node_types[node.type] = node_types.get(node.type, 0) + 1
            languages[node.language] = languages.get(node.language, 0) + 1

        for edge in self._edges:
            edge_types[edge.type] = edge_types.get(edge.type, 0) + 1

        return {
            "nodes": len(self._nodes),
            "edges": len(self._edges),
            "node_types": node_types,
            "edge_types": edge_types,
            "languages": languages,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0.0",
            "nodes": [asdict(node) for node in self._nodes.values()],
            "edges": [asdict(edge) for edge in self._edges],
        }

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, path: Path) -> "GraphStore":
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        graph = cls()
        for row in payload.get("nodes", []):
            graph.add_node(Node(**row))

        for row in payload.get("edges", []):
            graph.add_edge(Edge(**row))

        return graph
