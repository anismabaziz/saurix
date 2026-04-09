from __future__ import annotations

"""MCP tool business logic built on top of Code Atlas core services."""

import json
from pathlib import Path
from time import perf_counter

from ..graph import GraphStore
from ..indexer import build_graph
from ..query import callers_of, find_symbol, impact_of, related_files, shortest_path
from ..repo_source import prepare_repo_source
from .schemas import ToolError, ToolResult
from .utils import clamp_depth, clamp_limit, normalize_graph_path


def _format_error(exc: Exception, context: str = "") -> str:
    """Format exception with context for user-friendly error messages."""
    msg = f"{type(exc).__name__}: {exc}"
    if context:
        msg = f"{context}: {msg}"
    return msg


def index_repo(source: str, out: str | None = None) -> dict:
    """Index a repo source (local path or GitHub URL) and persist graph JSON."""
    t0 = perf_counter()
    try:
        out_path = normalize_graph_path(out)
        with prepare_repo_source(source) as (repo_path, source_kind):
            result = build_graph(repo_path)
            result.graph.write_json(out_path)
            stats = result.graph.stats()

        return ToolResult(
            ok=True,
            data={
                "graph_path": str(out_path),
                "source_kind": source_kind,
                "scanned_files": result.scanned_files,
                "indexed_files": result.indexed_files,
                "stats": stats,
            },
            meta={"duration_ms": int((perf_counter() - t0) * 1000)},
        ).to_dict()
    except FileNotFoundError as exc:
        return ToolResult(
            ok=False,
            error=ToolError(code="SOURCE_NOT_FOUND", message=f"Source path not found: {exc}"),
        ).to_dict()
    except PermissionError as exc:
        return ToolResult(
            ok=False,
            error=ToolError(code="PERMISSION_DENIED", message=f"Permission denied accessing source: {exc}"),
        ).to_dict()
    except ValueError as exc:
        return ToolResult(
            ok=False,
            error=ToolError(code="INVALID_SOURCE", message=f"Invalid source specification: {exc}"),
        ).to_dict()
    except Exception as exc:
        return ToolResult(
            ok=False,
            error=ToolError(code="INDEX_FAILED", message=_format_error(exc, "Indexing failed")),
        ).to_dict()


def stats(graph: str | None = None) -> dict:
    """Return graph statistics/quality metrics for a graph artifact."""
    t0 = perf_counter()
    try:
        g = GraphStore.from_json(normalize_graph_path(graph))
        return ToolResult(ok=True, data=g.stats(), meta={"duration_ms": int((perf_counter() - t0) * 1000)}).to_dict()
    except FileNotFoundError as exc:
        return ToolResult(
            ok=False,
            error=ToolError(code="GRAPH_NOT_FOUND", message=f"Graph file not found: {exc}"),
        ).to_dict()
    except json.JSONDecodeError as exc:
        return ToolResult(
            ok=False,
            error=ToolError(code="INVALID_GRAPH", message=f"Graph file contains invalid JSON: {exc}"),
        ).to_dict()
    except PermissionError as exc:
        return ToolResult(
            ok=False,
            error=ToolError(code="PERMISSION_DENIED", message=f"Permission denied reading graph: {exc}"),
        ).to_dict()
    except Exception as exc:
        return ToolResult(
            ok=False,
            error=ToolError(code="STATS_FAILED", message=_format_error(exc, "Failed to compute stats")),
        ).to_dict()


def find(graph: str | None, query: str, limit: int | None = None) -> dict:
    """Find nodes by fuzzy symbol query with bounded result size."""
    t0 = perf_counter()
    try:
        g = GraphStore.from_json(normalize_graph_path(graph))
        rows = find_symbol(g, query, limit=clamp_limit(limit, 20))
        return ToolResult(
            ok=True,
            data=rows,
            meta={"duration_ms": int((perf_counter() - t0) * 1000), "count": len(rows)},
        ).to_dict()
    except FileNotFoundError as exc:
        return ToolResult(
            ok=False,
            error=ToolError(code="GRAPH_NOT_FOUND", message=f"Graph file not found: {exc}"),
        ).to_dict()
    except json.JSONDecodeError as exc:
        return ToolResult(
            ok=False,
            error=ToolError(code="INVALID_GRAPH", message=f"Graph file contains invalid JSON: {exc}"),
        ).to_dict()
    except Exception as exc:
        return ToolResult(
            ok=False,
            error=ToolError(code="FIND_FAILED", message=_format_error(exc, "Symbol lookup failed")),
        ).to_dict()


def callers(graph: str | None, symbol: str, limit: int | None = None) -> dict:
    """Return reverse CALLS edges for a symbol identifier or name."""
    t0 = perf_counter()
    try:
        g = GraphStore.from_json(normalize_graph_path(graph))
        rows = callers_of(g, symbol, limit=clamp_limit(limit, 50))
        return ToolResult(
            ok=True,
            data=rows,
            meta={"duration_ms": int((perf_counter() - t0) * 1000), "count": len(rows)},
        ).to_dict()
    except FileNotFoundError as exc:
        return ToolResult(
            ok=False,
            error=ToolError(code="GRAPH_NOT_FOUND", message=f"Graph file not found: {exc}"),
        ).to_dict()
    except json.JSONDecodeError as exc:
        return ToolResult(
            ok=False,
            error=ToolError(code="INVALID_GRAPH", message=f"Graph file contains invalid JSON: {exc}"),
        ).to_dict()
    except Exception as exc:
        return ToolResult(
            ok=False,
            error=ToolError(code="CALLERS_FAILED", message=_format_error(exc, "Failed to find callers")),
        ).to_dict()


def path_between(graph: str | None, source: str, target: str, max_depth: int | None = None) -> dict:
    """Compute shortest directed path between two symbols."""
    t0 = perf_counter()
    try:
        g = GraphStore.from_json(normalize_graph_path(graph))
        rows = shortest_path(g, source, target, max_depth=clamp_depth(max_depth, 12))
        return ToolResult(
            ok=True,
            data=rows,
            meta={"duration_ms": int((perf_counter() - t0) * 1000), "count": len(rows)},
        ).to_dict()
    except FileNotFoundError as exc:
        return ToolResult(
            ok=False,
            error=ToolError(code="GRAPH_NOT_FOUND", message=f"Graph file not found: {exc}"),
        ).to_dict()
    except json.JSONDecodeError as exc:
        return ToolResult(
            ok=False,
            error=ToolError(code="INVALID_GRAPH", message=f"Graph file contains invalid JSON: {exc}"),
        ).to_dict()
    except Exception as exc:
        return ToolResult(
            ok=False,
            error=ToolError(code="PATH_FAILED", message=_format_error(exc, "Path computation failed")),
        ).to_dict()


def impact(graph: str | None, symbol: str, depth: int | None = None, limit: int | None = None) -> dict:
    """Estimate blast radius by reverse traversal from a symbol."""
    t0 = perf_counter()
    try:
        g = GraphStore.from_json(normalize_graph_path(graph))
        rows = impact_of(g, symbol, depth=clamp_depth(depth, 3), limit=clamp_limit(limit, 200))
        return ToolResult(
            ok=True,
            data=rows,
            meta={"duration_ms": int((perf_counter() - t0) * 1000), "count": len(rows)},
        ).to_dict()
    except FileNotFoundError as exc:
        return ToolResult(
            ok=False,
            error=ToolError(code="GRAPH_NOT_FOUND", message=f"Graph file not found: {exc}"),
        ).to_dict()
    except json.JSONDecodeError as exc:
        return ToolResult(
            ok=False,
            error=ToolError(code="INVALID_GRAPH", message=f"Graph file contains invalid JSON: {exc}"),
        ).to_dict()
    except Exception as exc:
        return ToolResult(
            ok=False,
            error=ToolError(code="IMPACT_FAILED", message=_format_error(exc, "Impact analysis failed")),
        ).to_dict()


def related(graph: str | None, file: str, depth: int | None = None, limit: int | None = None) -> dict:
    """Return file neighbors from bounded graph traversal around one file."""
    t0 = perf_counter()
    try:
        g = GraphStore.from_json(normalize_graph_path(graph))
        rows = related_files(g, file, depth=clamp_depth(depth, 2), limit=clamp_limit(limit, 100))
        return ToolResult(
            ok=True,
            data=rows,
            meta={"duration_ms": int((perf_counter() - t0) * 1000), "count": len(rows)},
        ).to_dict()
    except FileNotFoundError as exc:
        return ToolResult(
            ok=False,
            error=ToolError(code="GRAPH_NOT_FOUND", message=f"Graph file not found: {exc}"),
        ).to_dict()
    except json.JSONDecodeError as exc:
        return ToolResult(
            ok=False,
            error=ToolError(code="INVALID_GRAPH", message=f"Graph file contains invalid JSON: {exc}"),
        ).to_dict()
    except Exception as exc:
        return ToolResult(
            ok=False,
            error=ToolError(code="RELATED_FAILED", message=_format_error(exc, "Related files lookup failed")),
        ).to_dict()
