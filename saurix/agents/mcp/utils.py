"""
Shared guardrails/helpers for MCP tool handlers.
"""

from __future__ import annotations

from pathlib import Path

from ...core.config import config

DEFAULT_GRAPH = config.default_graph_path
MAX_LIMIT = config.max_limit
MAX_DEPTH = config.max_depth


def normalize_graph_path(path: str | None) -> Path:
    """
    Resolve optional graph path, falling back to default graph artifact.
    """
    return Path(path).resolve() if path else config.default_graph_path.resolve()


def clamp_limit(limit: int | None, default: int) -> int:
    """
    Bound result-size style arguments to a safe range.
    """
    value = default if limit is None else limit
    return max(1, min(value, config.max_limit))


def clamp_depth(depth: int | None, default: int) -> int:
    """
    Bound traversal-depth arguments to avoid unbounded graph walks.
    """
    value = default if depth is None else depth
    return max(1, min(value, config.max_depth))
