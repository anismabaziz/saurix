from __future__ import annotations

"""Graph-aware context builder for the conversational `ask` command."""

import re

from ..graph import GraphStore
from ..query import callers_of, find_symbol, impact_of, related_files


def build_question_context(graph: GraphStore, question: str, intent: str | None = None) -> dict[str, object]:
    """Build compact retrieval context tailored to question intent."""
    resolved_intent = intent or detect_question_intent(question)
    if resolved_intent == "overview":
        overview = _overview_context(graph)
        return {
            "intent": resolved_intent,
            "question": question,
            "overview": overview,
            "graph_stats": graph.stats(),
        }

    file_hint = _extract_file_hint(question)
    symbol_hint = _extract_symbol_hint(question)
    key = symbol_hint or file_hint or _extract_key_phrase(question)
    matches = find_symbol(graph, key, limit=12)

    top_symbol = matches[0]["id"] if matches else key
    callers = callers_of(graph, top_symbol, limit=12)
    impact = impact_of(graph, top_symbol, depth=3, limit=20)
    file_summary = _file_context(graph, file_hint) if file_hint else {}
    overview = _overview_context(graph)

    return {
        "intent": resolved_intent,
        "question": question,
        "seed": key,
        "file_hint": file_hint,
        "symbol_hint": symbol_hint,
        "top_symbol": top_symbol,
        "matches": matches,
        "callers": callers,
        "impact": impact,
        "file_context": file_summary,
        "overview": overview,
        "graph_stats": graph.stats(),
    }


def detect_question_intent(question: str) -> str:
    lowered = question.lower().strip()
    if not lowered:
        return "graph"

    normalized = re.sub(r"[^a-z0-9\s]", " ", lowered)
    normalized = " ".join(normalized.split())

    overview_terms = [
        "what is this repo",
        "what does this repo",
        "what is this project",
        "what does this project",
        "what does this project do",
        "what is the role of this project",
        "what is this for",
        "what is this tool for",
        "what does this tool do",
        "what is this codebase about",
        "what is this repository about",
        "what is the purpose",
        "what problem does this solve",
        "why does this exist",
        "what is the goal",
        "what does it do",
        "used for",
        "about this project",
        "about this repo",
        "overview",
        "high level",
        "big picture",
        "architecture",
        "purpose",
        "summary",
        "role",
        "intro",
    ]

    graph_terms = [
        "caller",
        "callers",
        "impact",
        "blast radius",
        "symbol",
        "function",
        "class",
        "method",
        "where is",
        "line",
        "path between",
        "related file",
        "edge",
        "node",
        "id",
    ]

    overview_score = sum(1 for term in overview_terms if term in normalized)
    graph_score = sum(1 for term in graph_terms if term in normalized)
    return "overview" if overview_score > graph_score else "graph"


def _extract_key_phrase(question: str) -> str:
    """Fallback keyword extraction when no file/symbol hint is provided."""
    cleaned = " ".join(question.strip().split())
    if not cleaned:
        return "main"
    parts = cleaned.replace("?", "").split()
    if len(parts) <= 3:
        return cleaned
    return " ".join(parts[-3:])


def _extract_file_hint(question: str) -> str | None:
    """Extract source-like file path token from natural language question."""
    match = re.search(r"([\w\-/]+\.(?:py|ts|tsx|go|java|js|jsx|rs|rb|php|cs))", question)
    if not match:
        return None
    return match.group(1)


def _extract_symbol_hint(question: str) -> str | None:
    """Extract explicit graph symbol id if present in question."""
    match = re.search(r"((?:python|typescript|go|java)://[^\s]+)", question)
    if not match:
        return None
    return match.group(1)


def _file_context(graph: GraphStore, file_hint: str) -> dict[str, object]:
    """Collect symbol/neighbor context scoped to one requested file."""
    nodes_for_file = [
        {
            "id": node.id,
            "type": node.type,
            "name": node.name,
            "line": node.line,
        }
        for node in graph.nodes.values()
        if (node.file == file_hint) or (node.file and node.file.endswith(file_hint))
    ]

    canonical_file = ""
    if nodes_for_file:
        raw = next((n for n in graph.nodes.values() if n.id == nodes_for_file[0]["id"]), None)
        canonical_file = raw.file or file_hint

    related = related_files(graph, canonical_file or file_hint, depth=2, limit=20)
    return {
        "requested_file": file_hint,
        "resolved_file": canonical_file or file_hint,
        "symbols_in_file": nodes_for_file[:30],
        "related_files": related,
    }


def _overview_context(graph: GraphStore) -> dict[str, object]:
    """Provide repository-level context for broad questions."""
    counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    language_counts: dict[str, int] = {}
    degree: dict[str, int] = {}

    for node in graph.nodes.values():
        if not node.file:
            continue
        counts[node.file] = counts.get(node.file, 0) + 1
        type_counts[node.type] = type_counts.get(node.type, 0) + 1
        language_counts[node.language] = language_counts.get(node.language, 0) + 1

    for edge in graph.edges:
        degree[edge.source] = degree.get(edge.source, 0) + 1
        degree[edge.target] = degree.get(edge.target, 0) + 1

    top_files = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:8]
    top_symbols: list[dict[str, object]] = []
    for node_id, deg in sorted(degree.items(), key=lambda kv: kv[1], reverse=True)[:10]:
        node = graph.nodes.get(node_id)
        if node is None:
            continue
        top_symbols.append(
            {
                "id": node.id,
                "type": node.type,
                "name": node.name,
                "file": node.file,
                "degree": deg,
            }
        )

    return {
        "top_files_by_symbol_count": [{"file": f, "symbols": c} for f, c in top_files],
        "node_types": type_counts,
        "languages": language_counts,
        "top_symbols_by_degree": top_symbols,
    }
