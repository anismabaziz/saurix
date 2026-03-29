from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .cli_render import render_stats_panel, render_table
from .cli_ui import UI, print_json
from .graph import GraphStore
from .indexer import build_graph
from .query import callers_of, find_symbol, impact_of, related_files, shortest_path
from .repo_source import prepare_repo_source


@dataclass
class ShellState:
    ui: UI
    graph_path: Path
    loaded_graph: GraphStore | None
    raw_mode: bool = False


def cmd_where(state: ShellState) -> None:
    if state.loaded_graph:
        state.ui.info(f"Loaded graph: {state.graph_path}")
    else:
        state.ui.warn("No graph loaded")


def cmd_index(state: ShellState, rest: list[str]) -> None:
    if not rest:
        state.ui.warn("Usage: index <repo-or-github-url> [--out PATH]")
        return
    out = state.graph_path
    source = rest[0]
    if "--out" in rest:
        try:
            out = Path(rest[rest.index("--out") + 1]).resolve()
        except IndexError:
            state.ui.warn("Usage: index <repo-or-github-url> [--out PATH]")
            return

    try:
        with prepare_repo_source(source) as (repo_path, source_kind):
            state.ui.info(f"Preparing source: {source_kind}")
            result = build_graph(repo_path)
            result.graph.write_json(out)
            state.graph_path = out
            state.loaded_graph = result.graph
            stats = result.graph.stats()
    except (ValueError, RuntimeError) as exc:
        state.ui.error(f"Index failed: {exc}")
        return

    state.ui.success("Index completed")
    print(f"  Source      : {source}")
    print(f"  Resolved    : {repo_path}")
    print(f"  Output      : {state.graph_path}")
    print(f"  Scanned     : {result.scanned_files}")
    print(f"  Indexed     : {result.indexed_files}")
    print(f"  Nodes/Edges : {stats['nodes']} / {stats['edges']}")


def cmd_load(state: ShellState, rest: list[str]) -> None:
    candidate = Path(rest[0]).resolve() if rest else state.graph_path
    if not candidate.exists():
        state.ui.error(f"Graph file not found: {candidate}")
        return
    state.loaded_graph = GraphStore.from_json(candidate)
    state.graph_path = candidate
    state.ui.success(f"Loaded graph: {state.graph_path}")


def cmd_stats(state: ShellState) -> None:
    if state.loaded_graph is None:
        state.ui.warn("No graph loaded. Run 'index <repo-or-github-url>' or 'load [PATH]' first.")
        return
    stats = state.loaded_graph.stats()
    if state.raw_mode:
        print_json(stats)
    else:
        render_stats_panel(stats, state.ui)


def cmd_find(state: ShellState, rest: list[str]) -> None:
    if state.loaded_graph is None:
        state.ui.warn("No graph loaded. Run 'index <repo-or-github-url>' or 'load [PATH]' first.")
        return
    if not rest:
        state.ui.warn("Usage: find <name> [--limit N]")
        return
    limit = _parse_int_flag(rest, "--limit", 20)
    if limit is None:
        state.ui.warn("Usage: find <name> [--limit N]")
        return
    rows = find_symbol(state.loaded_graph, rest[0], limit=limit)
    if state.raw_mode:
        print_json(rows)
    else:
        render_table("Find Results", rows, [("type", "TYPE"), ("name", "NAME"), ("id", "ID"), ("file", "FILE")], state.ui)


def cmd_callers(state: ShellState, rest: list[str]) -> None:
    if state.loaded_graph is None:
        state.ui.warn("No graph loaded. Run 'index <repo-or-github-url>' or 'load [PATH]' first.")
        return
    if not rest:
        state.ui.warn("Usage: callers <symbol> [--limit N]")
        return
    limit = _parse_int_flag(rest, "--limit", 50)
    if limit is None:
        state.ui.warn("Usage: callers <symbol> [--limit N]")
        return
    rows = callers_of(state.loaded_graph, rest[0], limit=limit)
    if state.raw_mode:
        print_json(rows)
    else:
        render_table("Callers", rows, [("caller_name", "CALLER"), ("caller", "CALLER_ID"), ("line", "LINE"), ("confidence", "CONF")], state.ui)


def cmd_related(state: ShellState, rest: list[str]) -> None:
    if state.loaded_graph is None:
        state.ui.warn("No graph loaded. Run 'index <repo-or-github-url>' or 'load [PATH]' first.")
        return
    if not rest:
        state.ui.warn("Usage: related <file> [--depth N] [--limit N]")
        return
    depth = _parse_int_flag(rest, "--depth", 2)
    limit = _parse_int_flag(rest, "--limit", 100)
    if depth is None or limit is None:
        state.ui.warn("Usage: related <file> [--depth N] [--limit N]")
        return
    rows = [{"file": p} for p in related_files(state.loaded_graph, rest[0], depth=depth, limit=limit)]
    if state.raw_mode:
        print_json([row["file"] for row in rows])
    else:
        render_table("Related Files", rows, [("file", "FILE")], state.ui)


def cmd_path(state: ShellState, rest: list[str]) -> None:
    if state.loaded_graph is None:
        state.ui.warn("No graph loaded. Run 'index <repo-or-github-url>' or 'load [PATH]' first.")
        return
    if len(rest) < 2:
        state.ui.warn("Usage: path <from> <to> [--max-depth N]")
        return
    max_depth = _parse_int_flag(rest, "--max-depth", 12)
    if max_depth is None:
        state.ui.warn("Usage: path <from> <to> [--max-depth N]")
        return
    rows = shortest_path(state.loaded_graph, rest[0], rest[1], max_depth=max_depth)
    if state.raw_mode:
        print_json(rows)
    else:
        render_table("Path", rows, [("step", "STEP"), ("edge", "EDGE"), ("type", "TYPE"), ("name", "NAME"), ("id", "ID")], state.ui)


def cmd_impact(state: ShellState, rest: list[str]) -> None:
    if state.loaded_graph is None:
        state.ui.warn("No graph loaded. Run 'index <repo-or-github-url>' or 'load [PATH]' first.")
        return
    if not rest:
        state.ui.warn("Usage: impact <symbol> [--depth N] [--limit N]")
        return
    depth = _parse_int_flag(rest, "--depth", 3)
    limit = _parse_int_flag(rest, "--limit", 200)
    if depth is None or limit is None:
        state.ui.warn("Usage: impact <symbol> [--depth N] [--limit N]")
        return
    rows = impact_of(state.loaded_graph, rest[0], depth=depth, limit=limit)
    if state.raw_mode:
        print_json(rows)
    else:
        render_table("Blast Radius", rows, [("distance", "DIST"), ("via", "VIA"), ("type", "TYPE"), ("name", "NAME"), ("file", "FILE")], state.ui)


def _parse_int_flag(parts: list[str], flag: str, default: int) -> int | None:
    if flag not in parts:
        return default
    try:
        return int(parts[parts.index(flag) + 1])
    except (IndexError, ValueError):
        return None
