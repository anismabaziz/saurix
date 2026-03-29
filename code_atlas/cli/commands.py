from __future__ import annotations

"""Core interactive commands for querying and navigating the graph."""

from dataclasses import dataclass
from pathlib import Path

from .render import render_index_summary, render_stats_panel, render_table
from .ui import UI, print_json
from ..graph import GraphStore
from ..indexer import build_graph
from ..query import callers_of, find_symbol, impact_of, related_files, shortest_path
from ..repo_source import prepare_repo_source


@dataclass
class ShellState:
    ui: UI
    graph_path: Path
    loaded_graph: GraphStore | None
    raw_mode: bool = False
    provider: str = "google"
    model: str | None = None


def cmd_where(state: ShellState) -> None:
    """Print active graph file path if loaded."""
    state.ui.info(f"Loaded graph: {state.graph_path}") if state.loaded_graph else state.ui.warn("No graph loaded")


def cmd_index(state: ShellState, rest: list[str]) -> None:
    """Index a local path or GitHub URL and persist graph output."""
    if not rest:
        state.ui.warn("Usage: index <repo-or-github-url> [--out PATH]")
        return
    out = Path(rest[rest.index("--out") + 1]).resolve() if "--out" in rest and len(rest) > rest.index("--out") + 1 else state.graph_path
    source = rest[0]
    try:
        with prepare_repo_source(source) as (repo_path, source_kind):
            state.ui.info(f"Preparing source: {source_kind}")
            result = build_graph(repo_path)
            result.graph.write_json(out)
            state.graph_path, state.loaded_graph = out, result.graph
            stats = result.graph.stats()
    except (ValueError, RuntimeError) as exc:
        state.ui.error(f"Index failed: {exc}")
        return
    state.ui.success("Index completed")
    summary: dict[str, object] = {
        "source": source,
        "resolved": repo_path,
        "output": state.graph_path,
        "scanned_files": result.scanned_files,
        "indexed_files": result.indexed_files,
        "nodes": stats.get("nodes", 0) if isinstance(stats, dict) else 0,
        "edges": stats.get("edges", 0) if isinstance(stats, dict) else 0,
    }
    inc = stats.get("incremental_cache", {}) if isinstance(stats, dict) else {}
    if isinstance(inc, dict):
        summary["cache_hits"] = inc.get("cache_hits", 0)
        summary["reindexed_files"] = inc.get("reindexed_files", 0)
        summary["deleted_files"] = inc.get("deleted_files", 0)
    render_index_summary(summary, state.ui)


def cmd_load(state: ShellState, rest: list[str]) -> None:
    """Load an existing graph JSON into shell state."""
    candidate = Path(rest[0]).resolve() if rest else state.graph_path
    if not candidate.exists():
        state.ui.error(f"Graph file not found: {candidate}")
        return
    state.loaded_graph = GraphStore.from_json(candidate)
    state.graph_path = candidate
    state.ui.success(f"Loaded graph: {state.graph_path}")


def cmd_stats(state: ShellState) -> None:
    """Render stats panel or raw JSON based on shell mode."""
    if not _ensure_graph(state):
        return
    stats = state.loaded_graph.stats()
    print_json(stats, state.ui) if state.raw_mode else render_stats_panel(stats, state.ui)


def cmd_find(state: ShellState, rest: list[str]) -> None:
    """Fuzzy search symbols by name/id substring."""
    if not _ensure_graph(state) or not rest:
        state.ui.warn("Usage: find <name> [--limit N]")
        return
    limit = _parse_int_flag(rest, "--limit", 20)
    if limit is None:
        state.ui.warn("Usage: find <name> [--limit N]")
        return
    rows = find_symbol(state.loaded_graph, rest[0], limit=limit)
    print_json(rows, state.ui) if state.raw_mode else render_table("Find Results", rows, [("type", "TYPE"), ("name", "NAME"), ("id", "ID"), ("file", "FILE")], state.ui)


def cmd_callers(state: ShellState, rest: list[str]) -> None:
    """Show CALLS reverse edges into a symbol."""
    if not _ensure_graph(state) or not rest:
        state.ui.warn("Usage: callers <symbol> [--limit N]")
        return
    limit = _parse_int_flag(rest, "--limit", 50)
    if limit is None:
        state.ui.warn("Usage: callers <symbol> [--limit N]")
        return
    rows = callers_of(state.loaded_graph, rest[0], limit=limit)
    print_json(rows, state.ui) if state.raw_mode else render_table("Callers", rows, [("caller_name", "CALLER"), ("caller", "CALLER_ID"), ("line", "LINE"), ("confidence", "CONF")], state.ui)


def cmd_related(state: ShellState, rest: list[str]) -> None:
    """Traverse local neighborhood from a file and list related files."""
    if not _ensure_graph(state) or not rest:
        state.ui.warn("Usage: related <file> [--depth N] [--limit N]")
        return
    depth, limit = _parse_int_flag(rest, "--depth", 2), _parse_int_flag(rest, "--limit", 100)
    if depth is None or limit is None:
        state.ui.warn("Usage: related <file> [--depth N] [--limit N]")
        return
    rows = [{"file": p} for p in related_files(state.loaded_graph, rest[0], depth=depth, limit=limit)]
    print_json([row["file"] for row in rows], state.ui) if state.raw_mode else render_table("Related Files", rows, [("file", "FILE")], state.ui)


def cmd_path(state: ShellState, rest: list[str]) -> None:
    """Find shortest directed path between two symbols."""
    if not _ensure_graph(state) or len(rest) < 2:
        state.ui.warn("Usage: path <from> <to> [--max-depth N]")
        return
    max_depth = _parse_int_flag(rest, "--max-depth", 12)
    if max_depth is None:
        state.ui.warn("Usage: path <from> <to> [--max-depth N]")
        return
    rows = shortest_path(state.loaded_graph, rest[0], rest[1], max_depth=max_depth)
    print_json(rows, state.ui) if state.raw_mode else render_table("Path", rows, [("step", "STEP"), ("edge", "EDGE"), ("type", "TYPE"), ("name", "NAME"), ("id", "ID")], state.ui)


def cmd_impact(state: ShellState, rest: list[str]) -> None:
    """Estimate blast radius via reverse traversal from a symbol."""
    if not _ensure_graph(state) or not rest:
        state.ui.warn("Usage: impact <symbol> [--depth N] [--limit N]")
        return
    depth, limit = _parse_int_flag(rest, "--depth", 3), _parse_int_flag(rest, "--limit", 200)
    if depth is None or limit is None:
        state.ui.warn("Usage: impact <symbol> [--depth N] [--limit N]")
        return
    rows = impact_of(state.loaded_graph, rest[0], depth=depth, limit=limit)
    print_json(rows, state.ui) if state.raw_mode else render_table("Blast Radius", rows, [("distance", "DIST"), ("via", "VIA"), ("type", "TYPE"), ("name", "NAME"), ("file", "FILE")], state.ui)


def _ensure_graph(state: ShellState) -> bool:
    """Guard helper to ensure commands run with a loaded graph."""
    if state.loaded_graph is None:
        state.ui.warn("No graph loaded. Run 'index <repo-or-github-url>' or 'load [PATH]' first.")
        return False
    return True


def _parse_int_flag(parts: list[str], flag: str, default: int) -> int | None:
    """Parse optional integer flag value from command tokens."""
    if flag not in parts:
        return default
    try:
        return int(parts[parts.index(flag) + 1])
    except (IndexError, ValueError):
        return None
