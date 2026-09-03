from __future__ import annotations

"""
Discovery queries — single owner for all Graph queries.

This module merges the former `basic` and `traversal` splits so that
`find`, `callers`, `callees`, `related`, `path`, `impact`, and
`neighborhood` live together and share symbol resolution.
"""

from collections import defaultdict, deque
from typing import Any

from ..core.graph import GraphStore


def find_symbol(graph: GraphStore, needle: str, limit: int = 20) -> list[dict[str, str]]:
    """Fuzzy search symbols by substring of name or id."""
    q = needle.lower()
    rows: list[dict[str, str]] = []

    for node in graph.nodes.values():
        if q in node.name.lower() or q in node.id.lower():
            rows.append({"id": node.id, "type": node.type, "name": node.name, "file": node.file or ""})

    rows.sort(key=lambda r: (r["type"], r["id"]))
    return rows[:limit]


def _resolve_exact_ids(graph: GraphStore, symbol: str) -> list[str]:
    """Shared exact resolution: exact id, then exact name via index. No fuzzy fallback."""
    if symbol in graph.nodes:
        return [symbol]
    exact = [node.id for node in graph.get_nodes_by_name(symbol)]
    return exact


def resolve_symbol_ids(graph: GraphStore, symbol: str, limit: int = 25) -> list[str]:
    """
    Resolves a user-provided symbol name or ID to a list of matching graph node IDs.

    Resolution order:
    1. Exact ID match.
    2. Exact name match via indexed lookup.
    3. Fuzzy substring match.
    """
    exact = _resolve_exact_ids(graph, symbol)
    if exact:
        return exact[:limit]

    fuzzy = find_symbol(graph, symbol, limit=limit)
    return [row["id"] for row in fuzzy]


def callers_of(graph: GraphStore, symbol: str, limit: int = 50) -> list[dict[str, str]]:
    """Find CALLS edges targeting `symbol`, sharing exact resolution with traversal queries."""
    # Use exact resolution only to preserve pre-collapse semantics (no fuzzy callers)
    exact_ids = _resolve_exact_ids(graph, symbol)
    target_ids = set(exact_ids) if exact_ids else {symbol}

    rows: list[dict[str, str]] = []
    for edge in graph.edges:
        if edge.type != "CALLS" or edge.target not in target_ids:
            continue
        source = graph.nodes.get(edge.source)
        rows.append(
            {
                "caller": edge.source,
                "caller_name": source.name if source else edge.source,
                "line": str(edge.line or ""),
                "confidence": edge.confidence,
            }
        )

    rows.sort(key=lambda r: (r["confidence"], r["caller"]))
    return rows[:limit]


def callees_of(graph: GraphStore, symbol: str, limit: int = 50) -> list[dict[str, str]]:
    """List CALLS edges outgoing from `symbol`, sharing exact resolution."""
    exact_ids = _resolve_exact_ids(graph, symbol)
    target_ids = set(exact_ids) if exact_ids else {symbol}

    rows: list[dict[str, str]] = []
    for edge in graph.edges:
        if edge.type != "CALLS" or edge.source not in target_ids:
            continue
        target = graph.nodes.get(edge.target)
        rows.append(
            {
                "callee": edge.target,
                "callee_name": target.name if target else edge.target,
                "line": str(edge.line or ""),
                "confidence": edge.confidence,
            }
        )

    rows.sort(key=lambda r: (r["confidence"], r["callee"]))
    return rows[:limit]


def related_files(graph: GraphStore, file_path: str, depth: int = 2, limit: int = 100) -> list[str]:
    """Find files related to `file_path` via undirected graph neighborhood."""
    file_nodes = [n.id for n in graph.nodes.values() if n.file == file_path]
    if not file_nodes:
        return []

    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        adjacency[edge.source].add(edge.target)
        adjacency[edge.target].add(edge.source)

    visited = set(file_nodes)
    frontier = set(file_nodes)

    for _ in range(max(depth, 0)):
        next_frontier: set[str] = set()
        for node_id in frontier:
            for neigh in adjacency.get(node_id, set()):
                if neigh not in visited:
                    visited.add(neigh)
                    next_frontier.add(neigh)
        frontier = next_frontier
        if not frontier:
            break

    files = sorted(
        {
            graph.nodes[node_id].file
            for node_id in visited
            if node_id in graph.nodes and graph.nodes[node_id].file
        }
    )
    return files[:limit]


def shortest_path(
    graph: GraphStore,
    source_symbol: str,
    target_symbol: str,
    *,
    edge_types: set[str] | None = None,
    max_depth: int = 12,
) -> list[dict[str, str]]:
    """
    Finds the shortest directed path between two symbols using BFS.
    """
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
    """
    Calculates the blast radius of a symbol by traversing incoming edges.
    """
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
    """
    Extracts a local cluster of nodes and edges surrounding a symbol.
    """
    seeds = resolve_symbol_ids(graph, symbol)
    if not seeds:
        return [], []

    visited = set(seeds)
    frontier = set(seeds)
    for _ in range(max(depth, 0)):
        next_frontier: set[str] = set()
        for node_id in frontier:
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
