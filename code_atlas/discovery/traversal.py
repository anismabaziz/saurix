from __future__ import annotations

"""Graph traversal queries: symbol resolution, shortest path, impact, subgraph."""

from collections import defaultdict, deque
from typing import Any

from ..core.graph import GraphStore
from .basic import find_symbol


def resolve_symbol_ids(graph: GraphStore, symbol: str, limit: int = 25) -> list[str]:
    """Resolve user input to graph node IDs via exact then fuzzy matching."""
    if symbol in graph.nodes:
        return [symbol]

    exact = [node.id for node in graph.get_nodes_by_name(symbol)]
    if exact:
        return exact[:limit]

    fuzzy = find_symbol(graph, symbol, limit=limit)
    return [row["id"] for row in fuzzy]


def shortest_path(
    graph: GraphStore,
    source_symbol: str,
    target_symbol: str,
    *,
    edge_types: set[str] | None = None,
    max_depth: int = 12,
) -> list[dict[str, str]]:
    """Return shortest directed path steps between source and target symbols."""
    allowed = edge_types or {"CALLS", "IMPORTS", "CONTAINS", "INHERITS"}
    source_ids = resolve_symbol_ids(graph, source_symbol)
    target_ids = set(resolve_symbol_ids(graph, target_symbol))
    if not source_ids or not target_ids:
        return []

    queue: deque[tuple[str, int]] = deque()
    prev: dict[str, tuple[str | None, str | None]] = {}

    for sid in source_ids:
        queue.append((sid, 0))
        prev[sid] = (None, None)

    hit: str | None = None
    while queue:
        node_id, depth = queue.popleft()
        if node_id in target_ids:
            hit = node_id
            break
        if depth >= max_depth:
            continue

        for edge in graph.get_edges_from(node_id):
            if edge.type not in allowed:
                continue
            nxt = edge.target
            if nxt in prev:
                continue
            prev[nxt] = (node_id, edge.type)
            queue.append((nxt, depth + 1))

    if hit is None:
        return []

    chain: list[str] = []
    cursor = hit
    while cursor is not None:
        chain.append(cursor)
        cursor = prev[cursor][0]
    chain.reverse()

    result: list[dict[str, str]] = []
    for idx, node_id in enumerate(chain):
        node = graph.nodes.get(node_id)
        edge_type = prev[node_id][1] if idx > 0 else ""
        result.append(
            {
                "step": str(idx),
                "edge": edge_type or "",
                "id": node_id,
                "type": node.type if node else "unknown",
                "name": node.name if node else node_id,
                "file": (node.file if node else "") or "",
            }
        )

    return result


def impact_of(
    graph: GraphStore,
    symbol: str,
    *,
    depth: int = 3,
    limit: int = 200,
    edge_types: set[str] | None = None,
) -> list[dict[str, str]]:
    """Return reverse-neighborhood impact rows for a changed symbol."""
    allowed = edge_types or {"CALLS", "IMPORTS", "CONTAINS"}
    seeds = resolve_symbol_ids(graph, symbol)
    if not seeds:
        return []

    queue: deque[tuple[str, int]] = deque((seed, 0) for seed in seeds)
    visited = set(seeds)
    rows: list[dict[str, str]] = []

    while queue and len(rows) < limit:
        node_id, d = queue.popleft()
        if d >= depth:
            continue
        
        for edge in graph.get_edges_to(node_id):
            if edge.type not in allowed:
                continue
            parent = edge.source
            if parent in visited:
                continue
            visited.add(parent)
            queue.append((parent, d + 1))
            node = graph.nodes.get(parent)
            rows.append(
                {
                    "distance": str(d + 1),
                    "via": edge.type,
                    "id": parent,
                    "type": node.type if node else "unknown",
                    "name": node.name if node else parent,
                    "file": (node.file if node else "") or "",
                }
            )
            if len(rows) >= limit:
                break

    rows.sort(key=lambda r: (int(r["distance"]), r["type"], r["id"]))
    return rows[:limit]


def neighborhood_subgraph(
    graph: GraphStore,
    symbol: str,
    *,
    depth: int = 2,
    limit: int = 120,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build bounded undirected neighborhood for visualization/export."""
    seeds = resolve_symbol_ids(graph, symbol)
    if not seeds:
        return [], []

    visited = set(seeds)
    frontier = set(seeds)
    for _ in range(max(depth, 0)):
        next_frontier: set[str] = set()
        for node_id in frontier:
            # Undirected traversal using both forward and backward indexes
            neighbors = set()
            for e in graph.get_edges_from(node_id):
                neighbors.add(e.target)
            for e in graph.get_edges_to(node_id):
                neighbors.add(e.source)
            
            for neighbor in neighbors:
                if len(visited) >= limit:
                    break
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                next_frontier.add(neighbor)
        frontier = next_frontier
        if not frontier or len(visited) >= limit:
            break

    nodes: list[dict[str, Any]] = []
    for node_id in sorted(visited):
        node = graph.nodes.get(node_id)
        if node is None:
            continue
        nodes.append(
            {
                "id": node.id,
                "label": node.name,
                "type": node.type,
                "file": node.file or "",
                "language": node.language,
            }
        )

    edges: list[dict[str, Any]] = []
    # Collect edges where at least one endpoint is in our visited set (or both?)
    # Usually for a subgraph we want edges where BOTH are in visited.
    # To be efficient, we iterate over visited nodes and their outgoing edges.
    seen_edges = set()
    for node_id in visited:
        for edge in graph.get_edges_from(node_id):
            if edge.target in visited:
                edge_key = (edge.source, edge.target, edge.type)
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    edges.append(
                        {
                            "source": edge.source,
                            "target": edge.target,
                            "type": edge.type,
                            "confidence": edge.confidence,
                        }
                    )

    return nodes, edges
