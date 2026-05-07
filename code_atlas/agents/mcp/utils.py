from __future__ import annotations

"""Shared guardrails/helpers for MCP tool handlers."""

from pathlib import Path


DEFAULT_GRAPH = Path("tmp") / "code-atlas.graph.json"
MAX_LIMIT = 500
MAX_DEPTH = 20


def normalize_graph_path(path: str | None) -> Path:
    """Resolve optional graph path, falling back to default graph artifact."""
    return Path(path).resolve() if path else DEFAULT_GRAPH.resolve()


def clamp_limit(limit: int | None, default: int) -> int:
    """Bound result-size style arguments to a safe range."""
    value = default if limit is None else limit
    return max(1, min(value, MAX_LIMIT))


def clamp_depth(depth: int | None, default: int) -> int:
    """Bound traversal-depth arguments to avoid unbounded graph walks."""
    value = default if depth is None else depth
    return max(1, min(value, MAX_DEPTH))
