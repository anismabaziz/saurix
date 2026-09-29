"""
MCP Tool Handlers

This module provides the core logic for the Model Context Protocol (MCP) server.
Each function here corresponds to a specific 'tool' that an AI agent can call
to interact with the Saurix knowledge graph.

The handlers wrap Saurix core services (indexing, discovery) and provide
standardized ToolResult/ToolError responses that AI agents can easily consume.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import wraps
from time import perf_counter
from typing import Any

from ...core.config import config
from ...core.graph import GraphStore
from ...core.indexing import build_graph
from ...core.source import prepare_repo_source
from ...discovery import (
    callees_of,
    callers_of,
    exact_symbol_ids,
    file_symbol_ids,
    find_symbol,
    impact_of,
    related_files,
    shortest_path,
)
from .schemas import ToolError, ToolResult
from .utils import clamp_depth, clamp_limit, normalize_graph_path


def _format_error(exc: Exception, context: str = "") -> str:
    """
    Helper to format exceptions into human-readable strings for tool errors.
    """
    msg = f"{type(exc).__name__}: {exc}"
    if context:
        msg = f"{context}: {msg}"
    return msg


def _failure(code: str, message: str, t0: float) -> dict:
    """
    Build the response envelope for a failure every caller can act on.

    Failures are timed like successes, so an agent never has to guess how long a
    call took from which of the two shapes came back.
    """
    return ToolResult(
        ok=False,
        error=ToolError(code=code, message=message),
        meta={"duration_ms": int((perf_counter() - t0) * 1000)},
    ).to_dict()


class UnreadableGraph(Exception):
    """
    Internal signal that a Graph could not be read, carrying the failure the tool
    hands back to the agent.
    """

    def __init__(self, code: str, message: str, t0: float) -> None:
        """
        Hold the failure itself, timed from the moment the call started.
        """
        super().__init__(message)
        self.response = _failure(code, message, t0)


def _reads_graph(handler: Callable[..., dict]) -> Callable[..., dict]:
    """
    Turn a graph-reading failure into the response the agent gets.

    Every tool that reads a Graph reports a bad path the same way, so this
    belongs at the boundary rather than inside each handler. A handler re-raises
    the signal instead of catching it, so a graph nobody could read is never
    reported as a failure of the query that never ran.
    """

    @wraps(handler)
    def wrapper(*args: Any, **kwargs: Any) -> dict:
        """
        Run the handler, returning the failure it raises for a bad graph.
        """
        try:
            return handler(*args, **kwargs)
        except UnreadableGraph as unreadable:
            return unreadable.response

    return wrapper


def _load_graph(graph: str | None, t0: float) -> GraphStore:
    """
    Read the Graph a tool was pointed at, naming the path in every failure.

    A file the loader cannot turn into a Graph is an invalid graph, not a crash:
    the file is there, it just is not one.
    """
    path = normalize_graph_path(graph)
    try:
        return GraphStore.from_json(path)
    except FileNotFoundError:
        raise UnreadableGraph(
            "GRAPH_NOT_FOUND",
            f"No graph at {path}. Run index_repo first, or pass the `graph` "
            f"argument the path of an existing one.",
            t0,
        ) from None
    except json.JSONDecodeError as exc:
        raise UnreadableGraph(
            "INVALID_GRAPH",
            f"{path} does not hold valid JSON ({exc}). Re-index the repository "
            f"to rewrite it.",
            t0,
        ) from exc
    except OSError as exc:
        raise UnreadableGraph(
            "GRAPH_UNREADABLE", f"Could not read the graph at {path}: {exc}", t0
        ) from exc
    except (AttributeError, TypeError, ValueError, KeyError) as exc:
        raise UnreadableGraph(
            "INVALID_GRAPH", f"{path} is not a Saurix graph: {_format_error(exc)}", t0
        ) from exc


def _success(rows: list, t0: float) -> dict:
    """
    Wrap a query's rows in the response envelope, timed and counted.
    """
    return ToolResult(
        ok=True,
        data=rows,
        meta={"duration_ms": int((perf_counter() - t0) * 1000), "count": len(rows)},
    ).to_dict()


def _unknown_symbol(symbol: str, t0: float, role: str = "symbol") -> dict:
    """
    Report a symbol the graph does not hold, pointing at the tool that finds the
    right one.

    Tools that take a symbol want it named exactly, so a partial name is a miss
    rather than a best guess: answering about a different symbol than the one
    asked for is worse than saying it is not there.
    """
    return _failure(
        "SYMBOL_NOT_FOUND",
        f"No {role} matches {symbol!r}. Call find_symbol to look for a close "
        f"match, or pass an id from the graph.",
        t0,
    )


def _unknown_file(file_path: str, t0: float) -> dict:
    """
    Report a file the graph does not hold.
    """
    return _failure(
        "FILE_NOT_FOUND",
        f"No symbol in the graph belongs to {file_path!r}. Call find_symbol to "
        f"list the files the graph indexed.",
        t0,
    )


def index_repo(source: str, out: str | None = None) -> dict:
    """
    Indexes a code repository and persists the result to a graph file.

    Args:
        source: Local path or GitHub URL to index.
        out: Optional destination path for the graph JSON.

    Returns:
        A ToolResult dictionary containing indexing statistics.
    """
    t0 = perf_counter()
    try:
        out_path = normalize_graph_path(out)
        # prepare_repo_source handles local paths and automatic GitHub cloning
        with prepare_repo_source(source) as (repo_path, source_kind):
            result = build_graph(repo_path)
            result.graph.write_json(out_path)
            stats_data = result.graph.stats()

        return ToolResult(
            ok=True,
            data={
                "graph_path": str(out_path),
                "source_kind": source_kind,
                "scanned_files": result.scanned_files,
                "indexed_files": result.indexed_files,
                "stats": stats_data,
            },
            meta={"duration_ms": int((perf_counter() - t0) * 1000)},
        ).to_dict()

    except FileNotFoundError as exc:
        return _failure("SOURCE_NOT_FOUND", f"Source path not found: {exc}", t0)
    except PermissionError as exc:
        return _failure(
            "PERMISSION_DENIED", f"Permission denied accessing source: {exc}", t0
        )
    except ValueError as exc:
        return _failure("INVALID_SOURCE", f"Invalid source specification: {exc}", t0)
    except Exception as exc:
        return _failure("INDEX_FAILED", _format_error(exc, "Indexing failed"), t0)


@_reads_graph
def stats(graph: str | None = None) -> dict:
    """
    Returns high-level statistics about the specified graph.
    """
    t0 = perf_counter()
    try:
        g = _load_graph(graph, t0)
        return ToolResult(
            ok=True,
            data=g.stats(),
            meta={"duration_ms": int((perf_counter() - t0) * 1000)},
        ).to_dict()
    except UnreadableGraph:
        raise
    except Exception as exc:
        return _failure(
            "STATS_FAILED", _format_error(exc, "Failed to compute stats"), t0
        )


@_reads_graph
def find(graph: str | None, query: str, limit: int | None = None) -> dict:
    """
    Performs a fuzzy search for symbols (functions, classes, etc.) in the graph.

    A query that matches nothing is an empty result, not a failure: this tool is
    how a caller discovers what the graph calls a symbol, so a miss is an answer.
    """
    t0 = perf_counter()
    try:
        g = _load_graph(graph, t0)
        return _success(
            find_symbol(g, query, limit=clamp_limit(limit, config.default_find_limit)),
            t0,
        )
    except UnreadableGraph:
        raise
    except Exception as exc:
        return _failure("FIND_FAILED", _format_error(exc, "Symbol lookup failed"), t0)


@_reads_graph
def callers(graph: str | None, symbol: str, limit: int | None = None) -> dict:
    """
    Identifies all functions or modules that call the specified symbol.
    """
    t0 = perf_counter()
    try:
        g = _load_graph(graph, t0)
        if not exact_symbol_ids(g, symbol):
            return _unknown_symbol(symbol, t0)
        return _success(
            callers_of(
                g, symbol, limit=clamp_limit(limit, config.default_callers_limit)
            ),
            t0,
        )
    except UnreadableGraph:
        raise
    except Exception as exc:
        return _failure(
            "CALLERS_FAILED", _format_error(exc, "Failed to find callers"), t0
        )


@_reads_graph
def callees(graph: str | None, symbol: str, limit: int | None = None) -> dict:
    """
    Identifies all functions or modules that are called by the specified symbol.
    """
    t0 = perf_counter()
    try:
        g = _load_graph(graph, t0)
        if not exact_symbol_ids(g, symbol):
            return _unknown_symbol(symbol, t0)
        return _success(
            callees_of(
                g, symbol, limit=clamp_limit(limit, config.default_callees_limit)
            ),
            t0,
        )
    except UnreadableGraph:
        raise
    except Exception as exc:
        return _failure(
            "CALLEES_FAILED", _format_error(exc, "Failed to find callees"), t0
        )


@_reads_graph
def path_between(
    graph: str | None, source: str, target: str, max_depth: int | None = None
) -> dict:
    """
    Finds the shortest dependency or call path between two symbols.

    Both ends have to resolve to a symbol the graph holds. A pair it holds but
    does not connect is a successful query with no path, since nothing failed.
    """
    t0 = perf_counter()
    try:
        g = _load_graph(graph, t0)
        for role, endpoint in (("source", source), ("target", target)):
            if not exact_symbol_ids(g, endpoint):
                return _unknown_symbol(endpoint, t0, role=role)
        return _success(
            shortest_path(
                g,
                source,
                target,
                max_depth=clamp_depth(max_depth, config.default_path_max_depth),
            ),
            t0,
        )
    except UnreadableGraph:
        raise
    except Exception as exc:
        return _failure(
            "PATH_FAILED", _format_error(exc, "Path computation failed"), t0
        )


@_reads_graph
def impact(
    graph: str | None, symbol: str, depth: int | None = None, limit: int | None = None
) -> dict:
    """
    Estimates the potential blast radius of changing a specific symbol.
    """
    t0 = perf_counter()
    try:
        g = _load_graph(graph, t0)
        if not exact_symbol_ids(g, symbol):
            return _unknown_symbol(symbol, t0)
        return _success(
            impact_of(
                g,
                symbol,
                depth=clamp_depth(depth, config.default_impact_depth),
                limit=clamp_limit(limit, config.default_impact_limit),
            ),
            t0,
        )
    except UnreadableGraph:
        raise
    except Exception as exc:
        return _failure(
            "IMPACT_FAILED", _format_error(exc, "Impact analysis failed"), t0
        )


@_reads_graph
def related(
    graph: str | None, file: str, depth: int | None = None, limit: int | None = None
) -> dict:
    """
    Identifies files that are structurally or behaviorally related to the
    specified file.
    """
    t0 = perf_counter()
    try:
        g = _load_graph(graph, t0)
        if not file_symbol_ids(g, file):
            return _unknown_file(file, t0)
        return _success(
            related_files(
                g,
                file,
                depth=clamp_depth(depth, config.default_related_depth),
                limit=clamp_limit(limit, config.default_related_limit),
            ),
            t0,
        )
    except UnreadableGraph:
        raise
    except Exception as exc:
        return _failure(
            "RELATED_FAILED", _format_error(exc, "Related files lookup failed"), t0
        )
