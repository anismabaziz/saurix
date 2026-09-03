from __future__ import annotations

"""Interactive commands for export and browser visualization."""

from pathlib import Path

from .commands import ShellState
from .flags import parse_int_flag, parse_path_flag
from ..discovery.visual import generate_visualization
from ..exporters import export_graphml, export_neo4j_csv
from ..infra.config import config


def cmd_visual(state: ShellState, rest: list[str]) -> None:
    """Generate and open a lightweight HTML graph visualization."""
    if state.loaded_graph is None:
        state.ui.warn("No graph loaded. Run 'index <repo-or-github-url>' or 'load [PATH]' first.")
        return

    out = parse_path_flag(rest, "--out", Path("tmp") / "viz.html")
    limit = parse_int_flag(rest, "--limit", config.default_visual_limit)
    if limit is None:
        state.ui.warn("Usage: visual [--out PATH] [--limit N]")
        return
    
    try:
        viz_path = generate_visualization(state.loaded_graph, out, limit=limit)
        state.ui.success(f"Visualization generated: {viz_path}")
        
        if "--no-open" not in rest:
            import webbrowser
            webbrowser.open(f"file://{viz_path.resolve()}")
    except Exception as exc:
        state.ui.error(f"Visualization failed: {exc}")


def cmd_export(state: ShellState, rest: list[str]) -> None:
    """Export active graph as GraphML or Neo4j CSV files."""
    if state.loaded_graph is None:
        state.ui.warn("No graph loaded. Run 'index <repo-or-github-url>' or 'load [PATH]' first.")
        return
    if not rest:
        state.ui.warn("Usage: export graphml [--out PATH] | export neo4j [--out DIR]")
        return

    fmt = rest[0].lower()
    if fmt == "graphml":
        out = parse_path_flag(rest, "--out", Path("tmp") / "saurix.graphml")
        state.ui.success(f"GraphML exported: {export_graphml(state.loaded_graph, out)}")
    elif fmt == "neo4j":
        out_dir = parse_path_flag(rest, "--out", Path("tmp") / "neo4j")
        nodes_csv, edges_csv = export_neo4j_csv(state.loaded_graph, out_dir)
        state.ui.success(f"Neo4j CSV exported: {nodes_csv} and {edges_csv}")
    else:
        state.ui.warn("Unknown export format. Use 'graphml' or 'neo4j'.")
