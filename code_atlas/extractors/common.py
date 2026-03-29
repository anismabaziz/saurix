from __future__ import annotations

from ..graph import GraphStore
from ..models import Edge, Node


def add_contains_edge(
    graph: GraphStore,
    *,
    language: str,
    source: str,
    target: str,
    file: str,
    line: int | None,
) -> None:
    graph.add_edge(
        Edge(
            type="CONTAINS",
            source=source,
            target=target,
            language=language,
            confidence="high",
            file=file,
            line=line,
        )
    )


def add_import_edge(
    graph: GraphStore,
    *,
    language: str,
    source: str,
    target: str,
    file: str,
    line: int | None,
) -> None:
    graph.add_edge(
        Edge(
            type="IMPORTS",
            source=source,
            target=target,
            language=language,
            confidence="high",
            file=file,
            line=line,
        )
    )


def add_calls_edge(
    graph: GraphStore,
    *,
    language: str,
    source: str,
    target: str,
    file: str,
    line: int | None,
    confidence: str = "medium",
) -> None:
    graph.add_edge(
        Edge(
            type="CALLS",
            source=source,
            target=target,
            language=language,
            confidence=confidence,
            file=file,
            line=line,
        )
    )


def add_node(
    graph: GraphStore,
    *,
    node_id: str,
    node_type: str,
    language: str,
    name: str,
    file: str | None = None,
    line: int | None = None,
    metadata: dict | None = None,
) -> None:
    graph.add_node(
        Node(
            id=node_id,
            type=node_type,
            language=language,
            name=name,
            file=file,
            line=line,
            metadata=metadata,
        )
    )
