from __future__ import annotations

"""Interactive commands for export and browser visualization."""

from pathlib import Path

from .commands import ShellState
from ..discovery.visual import generate_visualization
from ..exporters import export_graphml, export_neo4j_csv


def cmd_visual(state: ShellState, rest: list[str]) -> None:
    """Generate and open a lightweight HTML graph visualization."""
    if state.loaded_graph is None:
        state.ui.warn("No graph loaded. Run 'index <repo-or-github-url>' or 'load [PATH]' first.")
        return
    
    out = _parse_path_flag(rest, "--out", Path("tmp") / "viz.html")
    limit = _parse_int_flag(rest, "--limit", 5000)
    
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
        out = _parse_path_flag(rest, "--out", Path("tmp") / "saurix.graphml")
        state.ui.success(f"GraphML exported: {export_graphml(state.loaded_graph, out)}")
    elif fmt == "neo4j":
        out_dir = _parse_path_flag(rest, "--out", Path("tmp") / "neo4j")
        nodes_csv, edges_csv = export_neo4j_csv(state.loaded_graph, out_dir)
        state.ui.success(f"Neo4j CSV exported: {nodes_csv} and {edges_csv}")
    else:
        state.ui.warn("Unknown export format. Use 'graphml' or 'neo4j'.")


def _parse_int_flag(parts: list[str], flag: str, default: int) -> int | None:
    """Parse optional integer flag value from command tokens."""
    if flag not in parts:
        return default
    try:
        return int(parts[parts.index(flag) + 1])
    except (IndexError, ValueError):
        return None


def _parse_path_flag(parts: list[str], flag: str, default: Path) -> Path:
    """Parse optional path flag value from command tokens."""
    if flag not in parts:
        return default.resolve()
    try:
        return Path(parts[parts.index(flag) + 1]).resolve()
    except IndexError:
        return default.resolve()
