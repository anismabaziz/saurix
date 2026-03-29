from __future__ import annotations

from pathlib import Path

from .cli_commands import ShellState
from .exporters import build_visual_html, export_graphml, export_neo4j_csv


def cmd_export(state: ShellState, rest: list[str]) -> None:
    if state.loaded_graph is None:
        state.ui.warn("No graph loaded. Run 'index <repo-or-github-url>' or 'load [PATH]' first.")
        return
    if not rest:
        state.ui.warn("Usage: export graphml [--out PATH] | export neo4j [--out DIR]")
        return

    format_name = rest[0].lower()
    if format_name == "graphml":
        out = parse_path_flag(rest, "--out", Path("tmp") / "code-atlas.graphml")
        path = export_graphml(state.loaded_graph, out)
        state.ui.success(f"GraphML exported: {path}")
        return
    if format_name == "neo4j":
        out_dir = parse_path_flag(rest, "--out", Path("tmp") / "neo4j")
        nodes_csv, edges_csv = export_neo4j_csv(state.loaded_graph, out_dir)
        state.ui.success(f"Neo4j CSV exported: {nodes_csv} and {edges_csv}")
        return
    state.ui.warn("Unknown export format. Use 'graphml' or 'neo4j'.")


def cmd_visual(state: ShellState, rest: list[str]) -> None:
    if state.loaded_graph is None:
        state.ui.warn("No graph loaded. Run 'index <repo-or-github-url>' or 'load [PATH]' first.")
        return
    if not rest:
        state.ui.warn("Usage: visual <symbol> [--depth N] [--limit N] [--out PATH]")
        return

    depth = parse_int_flag(rest, "--depth", 2)
    limit = parse_int_flag(rest, "--limit", 120)
    out = parse_path_flag(rest, "--out", Path("tmp") / "graph-view.html")
    if depth is None or limit is None:
        state.ui.warn("Usage: visual <symbol> [--depth N] [--limit N] [--out PATH]")
        return

    html_path = build_visual_html(state.loaded_graph, rest[0], out, depth=depth, limit=limit, open_browser=True)
    state.ui.success(f"Opened interactive graph: {html_path}")


def parse_int_flag(parts: list[str], flag: str, default: int) -> int | None:
    if flag not in parts:
        return default
    try:
        return int(parts[parts.index(flag) + 1])
    except (IndexError, ValueError):
        return None


def parse_path_flag(parts: list[str], flag: str, default: Path) -> Path:
    if flag not in parts:
        return default.resolve()
    try:
        return Path(parts[parts.index(flag) + 1]).resolve()
    except IndexError:
        return default.resolve()
