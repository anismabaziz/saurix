from __future__ import annotations

from collections import defaultdict

from .graph import GraphStore


def find_symbol(graph: GraphStore, needle: str, limit: int = 20) -> list[dict[str, str]]:
    q = needle.lower()
    rows: list[dict[str, str]] = []

    for node in graph.nodes.values():
        if q in node.name.lower() or q in node.id.lower():
            rows.append({"id": node.id, "type": node.type, "name": node.name, "file": node.file or ""})

    rows.sort(key=lambda r: (r["type"], r["id"]))
    return rows[:limit]


def callers_of(graph: GraphStore, symbol: str, limit: int = 50) -> list[dict[str, str]]:
    target_ids = {symbol}
    for node in graph.nodes.values():
        if node.name == symbol:
            target_ids.add(node.id)

    rows: list[dict[str, str]] = []
    for edge in graph.edges:
        if edge.type != "CALLS":
            continue
        if edge.target not in target_ids:
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


def related_files(graph: GraphStore, file_path: str, depth: int = 2, limit: int = 100) -> list[str]:
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

    files = sorted({graph.nodes[node_id].file for node_id in visited if node_id in graph.nodes and graph.nodes[node_id].file})
    return files[:limit]
