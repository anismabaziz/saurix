from __future__ import annotations

"""
Core interactive commands for querying and navigating the graph.
"""

from dataclasses import dataclass
from pathlib import Path

from .parse import parse_csv_flag, parse_int_flag, parse_path_flag
from .ui import UI, print_json, render_index_summary, render_stats_panel, render_table
from ..core.config import config
from ..core.graph import GraphStore
from ..core.indexing import build_graph
from ..core.source import prepare_repo_source
from ..discovery import callees_of, callers_of, find_symbol, impact_of, related_files, shortest_path
from ..discovery.visual import generate_visualization


@dataclass
class ShellState:
    ui: UI
    graph_path: Path
    loaded_graph: GraphStore | None
    raw_mode: bool = False


def cmd_where(state: ShellState) -> None:
    """
    Print active graph file path if loaded.
    """
    state.ui.info(f"Loaded graph: {state.graph_path}") if state.loaded_graph else state.ui.warn("No graph loaded")


def cmd_index(state: ShellState, rest: list[str]) -> None:
    """
    Index a local path or GitHub URL and persist graph output.
    """
    if not rest:
        state.ui.warn("Usage: index <repo-or-github-url> [--out PATH]")
        return
    out = parse_path_flag(rest, "--out", state.graph_path)
    excludes = parse_csv_flag(rest, "--exclude")
    source = rest[0]
    try:
        with prepare_repo_source(source) as (repo_path, source_kind):
            state.ui.info(f"Preparing source: {source_kind}")
            if source_kind == "github":
                state.ui.info(f"Cloned to: {repo_path}")

            state.ui.info("Scanning files...")
            state.ui.progress_line_start("Indexing files...")

            def on_file_indexed(done: int, total: int, rel: str) -> None:
                short_rel = rel if len(rel) <= 70 else f"...{rel[-67:]}"
                state.ui.progress_line_update(done, total, short_rel)

            result = build_graph(repo_path, exclude_dirs=excludes, on_file_indexed=on_file_indexed)
            if result.scanned_files == 0:
                state.ui.progress_line_finish("Indexing files... 0/0 (100%)")
                state.ui.warn("No source files found")
            else:
                state.ui.progress_line_finish()

            state.ui.info("Writing graph...")
            result.graph.write_json(out)
            state.graph_path, state.loaded_graph = out, result.graph
            stats = result.graph.stats()
    except (ValueError, RuntimeError) as exc:
        state.ui.error(f"Index failed: {exc}")
        return
    except Exception as exc:
        state.ui.error(f"Unexpected error during indexing: {exc}")
        return

    state.ui.success("Index completed")
    summary: dict[str, object] = {
        "source": source,
        "resolved": str(repo_path),
        "output": str(state.graph_path),
        "scanned_files": result.scanned_files,
        "indexed_files": result.indexed_files,
        "nodes": stats.get("nodes", 0) if isinstance(stats, dict) else 0,
        "edges": stats.get("edges", 0) if isinstance(stats, dict) else 0,
    }
    if excludes:
        summary["excluded_dirs"] = ", ".join(sorted(excludes))
    render_index_summary(summary, state.ui)


def cmd_load(state: ShellState, rest: list[str]) -> None:
    """
    Load an existing graph JSON into shell state.
    """
    candidate = Path(rest[0]).resolve() if rest else state.graph_path
    if not candidate.exists():
        state.ui.error(f"Graph file not found: {candidate}")
        return
    state.loaded_graph = GraphStore.from_json(candidate)
    state.graph_path = candidate
    state.ui.success(f"Loaded graph: {state.graph_path}")


def cmd_stats(state: ShellState) -> None:
    """
    Render stats panel or raw JSON based on shell mode.
    """
    if not _ensure_graph(state):
        return
    stats = state.loaded_graph.stats()
    print_json(stats, state.ui) if state.raw_mode else render_stats_panel(stats, state.ui)


def cmd_find(state: ShellState, rest: list[str]) -> None:
    """
    Fuzzy search symbols by name/id substring.
    """
    if not _ensure_graph(state) or not rest:
        state.ui.warn("Usage: find <name> [--limit N]")
        return
    limit = parse_int_flag(rest, "--limit", config.default_find_limit)
    if limit is None:
        state.ui.warn("Usage: find <name> [--limit N]")
        return
    rows = find_symbol(state.loaded_graph, rest[0], limit=limit)
    print_json(rows, state.ui) if state.raw_mode else render_table("Find Results", rows, [("type", "TYPE"), ("name", "NAME"), ("id", "ID"), ("file", "FILE")], state.ui)


def cmd_callers(state: ShellState, rest: list[str]) -> None:
    """
    Show CALLS reverse edges into a symbol.
    """
    if not _ensure_graph(state) or not rest:
        state.ui.warn("Usage: callers <symbol> [--limit N]")
        return
    limit = parse_int_flag(rest, "--limit", config.default_callers_limit)
    if limit is None:
        state.ui.warn("Usage: callers <symbol> [--limit N]")
        return
    rows = callers_of(state.loaded_graph, rest[0], limit=limit)
    print_json(rows, state.ui) if state.raw_mode else render_table("Callers", rows, [("caller_name", "CALLER"), ("caller", "CALLER_ID"), ("line", "LINE"), ("confidence", "CONF")], state.ui)


def cmd_callees(state: ShellState, rest: list[str]) -> None:
    """
    Show CALLS outgoing edges from a symbol.
    """
    if not _ensure_graph(state) or not rest:
        state.ui.warn("Usage: callees <symbol> [--limit N]")
        return
    limit = parse_int_flag(rest, "--limit", config.default_callees_limit)
    if limit is None:
        state.ui.warn("Usage: callees <symbol> [--limit N]")
        return
    rows = callees_of(state.loaded_graph, rest[0], limit=limit)
    print_json(rows, state.ui) if state.raw_mode else render_table("Callees", rows, [("callee_name", "CALLEE"), ("callee", "CALLEE_ID"), ("line", "LINE"), ("confidence", "CONF")], state.ui)


def cmd_related(state: ShellState, rest: list[str]) -> None:
    """
    Traverse local neighborhood from a file and list related files.
    """
    if not _ensure_graph(state) or not rest:
        state.ui.warn("Usage: related <file> [--depth N] [--limit N]")
        return
    depth, limit = parse_int_flag(rest, "--depth", config.default_related_depth), parse_int_flag(rest, "--limit", config.default_related_limit)
    if depth is None or limit is None:
        state.ui.warn("Usage: related <file> [--depth N] [--limit N]")
        return
    rows = [{"file": p} for p in related_files(state.loaded_graph, rest[0], depth=depth, limit=limit)]
    print_json([row["file"] for row in rows], state.ui) if state.raw_mode else render_table("Related Files", rows, [("file", "FILE")], state.ui)


def cmd_path(state: ShellState, rest: list[str]) -> None:
    """
    Find shortest directed path between two symbols.
    """
    if not _ensure_graph(state) or len(rest) < 2:
        state.ui.warn("Usage: path <from> <to> [--max-depth N]")
        return
    max_depth = parse_int_flag(rest, "--max-depth", config.default_path_max_depth)
    if max_depth is None:
        state.ui.warn("Usage: path <from> <to> [--max-depth N]")
        return
    rows = shortest_path(state.loaded_graph, rest[0], rest[1], max_depth=max_depth)
    print_json(rows, state.ui) if state.raw_mode else render_table("Path", rows, [("step", "STEP"), ("edge", "EDGE"), ("type", "TYPE"), ("name", "NAME"), ("id", "ID")], state.ui)


def cmd_impact(state: ShellState, rest: list[str]) -> None:
    """
    Estimate blast radius via reverse traversal from a symbol.
    """
    if not _ensure_graph(state) or not rest:
        state.ui.warn("Usage: impact <symbol> [--depth N] [--limit N]")
        return
    depth, limit = parse_int_flag(rest, "--depth", config.default_impact_depth), parse_int_flag(rest, "--limit", config.default_impact_limit)
    if depth is None or limit is None:
        state.ui.warn("Usage: impact <symbol> [--depth N] [--limit N]")
        return
    rows = impact_of(state.loaded_graph, rest[0], depth=depth, limit=limit)
    print_json(rows, state.ui) if state.raw_mode else render_table("Blast Radius", rows, [("distance", "DIST"), ("via", "VIA"), ("type", "TYPE"), ("name", "NAME"), ("file", "FILE")], state.ui)


def cmd_init(state: ShellState) -> None:
    """
    Smooth, zero-config onboarding for the current project.
    """
    ui = state.ui
    ui.header("Initializing Saurix for this project...")

    # 1. Index current directory
    cwd = Path.cwd()
    ui.info(f"Indexing: {cwd}")
    cmd_index(state, [".", "--out", "saurix.graph.json"])

    if not state.loaded_graph:
        ui.error("Indexing failed. Cannot proceed with initialization.")
        return

    # 2. Generate visualization
    report_path = cwd / "saurix.html"
    ui.info(f"Generating dashboard: {report_path}")
    generate_visualization(state.loaded_graph, report_path)

    # 3. Provide MCP Config
    ui.success("Initialization complete!")
    ui.print()
    ui.header("Step 3: MCP Integration")
    ui.info("Add the following to your MCP client config:")

    # 1. Claude/Global Format
    ui.muted("\nFor Claude Desktop / Global MCP:")
    claude_config = {
        "mcpServers": {
            "saurix": {
                "command": "uv",
                "args": ["--directory", str(cwd), "run", "saurix-mcp"],
            }
        }
    }
    print_json(claude_config, ui)

    # 2. OpenCode Format
    ui.muted("\nFor OpenCode (~/.opencode/config.json):")
    opencode_config = {
        "mcp": {
            "saurix": {
                "type": "local",
                "command": ["uv", "--directory", str(cwd), "run", "saurix-mcp"],
                "enabled": True
            }
        }
    }
    print_json(opencode_config, ui)

    # 3. Cursor instructions
    ui.muted("\nFor Cursor (Settings -> Models -> MCP):")
    ui.print(f"  Name: saurix")
    ui.print(f"  Type: command")
    ui.print(f"  Command: uv --directory {cwd} run saurix-mcp")
    ui.print()
    ui.info(f"Open [bold]{report_path}[/] in your browser to see the 2D map.")


def cmd_visual(state: ShellState, rest: list[str]) -> None:
    """
    Generate and open a lightweight HTML graph visualization.
    """
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


def _ensure_graph(state: ShellState) -> bool:
    """
    Guard helper to ensure commands run with a loaded graph.
    """
    if state.loaded_graph is None:
        state.ui.warn("No graph loaded. Run 'index <repo-or-github-url>' or 'load [PATH]' first.")
        return False
    return True
