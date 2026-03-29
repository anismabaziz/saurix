from __future__ import annotations

from collections import deque
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


def resolve_symbol_ids(graph: GraphStore, symbol: str, limit: int = 25) -> list[str]:
    if symbol in graph.nodes:
        return [symbol]

    exact = [node.id for node in graph.nodes.values() if node.name == symbol]
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
    allowed = edge_types or {"CALLS", "IMPORTS", "CONTAINS", "INHERITS"}

    source_ids = resolve_symbol_ids(graph, source_symbol)
    target_ids = set(resolve_symbol_ids(graph, target_symbol))
    if not source_ids or not target_ids:
        return []

    adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for edge in graph.edges:
        if edge.type in allowed:
            adjacency[edge.source].append((edge.target, edge.type))

    queue: deque[tuple[str, int]] = deque()
    prev: dict[str, tuple[str | None, str | None]] = {}
    depth_by_node: dict[str, int] = {}

    for sid in source_ids:
        queue.append((sid, 0))
        prev[sid] = (None, None)
        depth_by_node[sid] = 0

    hit: str | None = None
    while queue:
        node_id, depth = queue.popleft()
        if node_id in target_ids:
            hit = node_id
            break
        if depth >= max_depth:
            continue

        for nxt, edge_type in adjacency.get(node_id, []):
            if nxt in prev:
                continue
            prev[nxt] = (node_id, edge_type)
            depth_by_node[nxt] = depth + 1
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
        edge_type = ""
        if idx > 0:
            edge_type = prev[node_id][1] or ""
        result.append(
            {
                "step": str(idx),
                "edge": edge_type,
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
    allowed = edge_types or {"CALLS", "IMPORTS", "CONTAINS"}
    seeds = resolve_symbol_ids(graph, symbol)
    if not seeds:
        return []

    reverse_adj: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for edge in graph.edges:
        if edge.type in allowed:
            reverse_adj[edge.target].append((edge.source, edge.type))

    queue: deque[tuple[str, int]] = deque((seed, 0) for seed in seeds)
    visited = set(seeds)
    rows: list[dict[str, str]] = []

    while queue and len(rows) < limit:
        node_id, d = queue.popleft()
        if d >= depth:
            continue

        for parent, via in reverse_adj.get(node_id, []):
            if parent in visited:
                continue
            visited.add(parent)
            queue.append((parent, d + 1))

            node = graph.nodes.get(parent)
            rows.append(
                {
                    "distance": str(d + 1),
                    "via": via,
                    "id": parent,
                    "type": node.type if node else "unknown",
                    "name": node.name if node else parent,
                    "file": (node.file if node else "") or "",
                }
            )

    rows.sort(key=lambda r: (int(r["distance"]), r["type"], r["id"]))
    return rows[:limit]


def neighborhood_subgraph(
    graph: GraphStore,
    symbol: str,
    *,
    depth: int = 2,
    limit: int = 120,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    seeds = resolve_symbol_ids(graph, symbol)
    if not seeds:
        return [], []

    undirected: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        undirected[edge.source].add(edge.target)
        undirected[edge.target].add(edge.source)

    visited = set(seeds)
    frontier = set(seeds)

    for _ in range(max(depth, 0)):
        next_frontier: set[str] = set()
        for node_id in frontier:
            for neighbor in undirected.get(node_id, set()):
                if len(visited) >= limit:
                    break
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                next_frontier.add(neighbor)
        frontier = next_frontier
        if not frontier or len(visited) >= limit:
            break

    nodes: list[dict[str, str]] = []
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

    edges: list[dict[str, str]] = []
    for edge in graph.edges:
        if edge.source in visited and edge.target in visited:
            edges.append(
                {
                    "source": edge.source,
                    "target": edge.target,
                    "type": edge.type,
                    "confidence": edge.confidence,
                }
            )

    return nodes, edges
