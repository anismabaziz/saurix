from __future__ import annotations

import argparse
import json
import shlex
import shutil
from pathlib import Path

from .exporters import build_visual_html, export_graphml, export_neo4j_csv
from .graph import GraphStore
from .indexer import build_graph
from .query import callers_of, find_symbol, impact_of, related_files, shortest_path
from .repo_source import prepare_repo_source


ASCII_LOGO = r"""
   ______          __        ___   __  __
  / ____/___  ____/ /__     /   | / /_/ /___ ______
 / /   / __ \/ __  / _ \   / /| |/ __/ / __ `/ ___/
/ /___/ /_/ / /_/ /  __/  / ___ / /_/ / /_/ (__  )
\____/\____/\__,_/\___/  /_/  |_\__/_/\__,_/____/
"""

DEFAULT_GRAPH_RELATIVE = Path("tmp") / "code-atlas.graph.json"


class UI:
    RESET = "\033[0m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"

    def __init__(self) -> None:
        self.use_color = self._supports_color()

    def _supports_color(self) -> bool:
        if not shutil.which("tput"):
            return False
        return True

    def c(self, text: str, color: str) -> str:
        if not self.use_color:
            return text
        return f"{color}{text}{self.RESET}"

    def header(self, text: str) -> None:
        print(self.c(text, self.BOLD + self.CYAN))

    def info(self, text: str) -> None:
        print(self.c(text, self.BLUE))

    def success(self, text: str) -> None:
        print(self.c(text, self.GREEN))

    def warn(self, text: str) -> None:
        print(self.c(text, self.YELLOW))

    def error(self, text: str) -> None:
        print(self.c(text, self.RED))

    def muted(self, text: str) -> None:
        print(self.c(text, self.DIM))


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _render_stats_panel(stats: dict[str, object], ui: UI) -> None:
    ui.header("\nGraph Stats")
    print("-" * 54)
    print(f"Nodes: {stats.get('nodes', 0):<10}Edges: {stats.get('edges', 0)}")

    node_types = stats.get("node_types", {})
    edge_types = stats.get("edge_types", {})
    languages = stats.get("languages", {})

    print("\nNode Types")
    print("-" * 54)
    for key, value in sorted(node_types.items()):
        print(f"{key:<20}{value}")

    print("\nEdge Types")
    print("-" * 54)
    for key, value in sorted(edge_types.items()):
        print(f"{key:<20}{value}")

    print("\nLanguages")
    print("-" * 54)
    for key, value in sorted(languages.items()):
        print(f"{key:<20}{value}")


def _render_table(title: str, rows: list[dict[str, str]], columns: list[tuple[str, str]], ui: UI) -> None:
    ui.header(f"\n{title}")
    if not rows:
        ui.warn("No results.")
        return

    widths: dict[str, int] = {}
    for key, label in columns:
        max_cell = max(len(str(row.get(key, ""))) for row in rows)
        widths[key] = max(len(label), min(max_cell, 60))

    header = " | ".join(label.ljust(widths[key]) for key, label in columns)
    separator = "-+-".join("-" * widths[key] for key, _ in columns)
    print(header)
    print(separator)

    for row in rows:
        values: list[str] = []
        for key, _label in columns:
            text = str(row.get(key, ""))
            if len(text) > widths[key]:
                text = text[: widths[key] - 3] + "..."
            values.append(text.ljust(widths[key]))
        print(" | ".join(values))


def _interactive_help() -> str:
    return "\n".join(
        [
            "Interactive commands:",
            "  help                                        Show this message",
            "  index <repo-or-github-url> [--out PATH]    Index source to graph JSON",
            "  load [PATH]                                 Load a graph JSON file",
            "  stats                                       Show graph statistics",
            "  find <name> [--limit N]                     Find symbol by fuzzy name",
            "  callers <symbol> [--limit N]                Show callers of a symbol",
            "  related <file> [--depth N] [--limit N]      Show related files",
            "  path <from> <to> [--max-depth N]            Trace shortest path between symbols",
            "  impact <symbol> [--depth N] [--limit N]     Show blast radius for symbol changes",
            "  export graphml [--out PATH]                 Export graph to GraphML",
            "  export neo4j [--out DIR]                    Export graph to Neo4j CSV files",
            "  visual <symbol> [--depth N] [--limit N]     Open interactive browser graph",
            "  where                                       Show current graph path",
            "  raw on|off                                  Toggle JSON raw output",
            "  clear                                       Clear the screen",
            "  exit | quit                                 Leave interactive mode",
        ]
    )


def _clear_screen() -> None:
    print("\033[2J\033[H", end="")


def _cmd_interactive(args: argparse.Namespace) -> int:
    graph_path = Path(getattr(args, "graph", str(DEFAULT_GRAPH_RELATIVE))).resolve()
    loaded_graph: GraphStore | None = None
    ui = UI()
    raw_mode = False

    if graph_path.exists():
        loaded_graph = GraphStore.from_json(graph_path)

    print(ui.c(ASCII_LOGO, ui.CYAN + ui.BOLD))
    ui.header("Code Atlas Interactive")
    ui.muted("Type 'help' for commands, 'exit' to quit.")

    while True:
        state = graph_path.name if loaded_graph else "no-graph"
        prompt = ui.c("atlas", ui.BOLD + ui.CYAN) + ui.c(f"[{state}]", ui.DIM)
        prompt += ui.c(" > ", ui.BOLD)

        try:
            raw = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not raw:
            continue

        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            ui.error(f"Parse error: {exc}")
            continue

        cmd = parts[0].lower()
        rest = parts[1:]

        if cmd in {"exit", "quit"}:
            ui.success("Goodbye.")
            return 0

        if cmd == "help":
            print(_interactive_help())
            continue

        if cmd == "clear":
            _clear_screen()
            print(ui.c(ASCII_LOGO, ui.CYAN + ui.BOLD))
            ui.header("Code Atlas Interactive")
            ui.muted("Type 'help' for commands, 'exit' to quit.")
            continue

        if cmd == "raw":
            if not rest or rest[0] not in {"on", "off"}:
                ui.warn("Usage: raw on|off")
                continue
            raw_mode = rest[0] == "on"
            ui.success(f"Raw JSON output: {'enabled' if raw_mode else 'disabled'}")
            continue

        if cmd == "where":
            if loaded_graph:
                ui.info(f"Loaded graph: {graph_path}")
            else:
                ui.warn("No graph loaded")
            continue

        if cmd == "index":
            if not rest:
                ui.warn("Usage: index <repo-or-github-url> [--out PATH]")
                continue
            out = graph_path
            source = rest[0]

            if "--out" in rest:
                try:
                    out = Path(rest[rest.index("--out") + 1]).resolve()
                except IndexError:
                    ui.warn("Usage: index <repo-or-github-url> [--out PATH]")
                    continue

            try:
                with prepare_repo_source(source) as (repo_path, source_kind):
                    ui.info(f"Preparing source: {source_kind}")
                    result = build_graph(repo_path)
                    result.graph.write_json(out)
                    graph_path = out
                    loaded_graph = result.graph
                    stats = result.graph.stats()
            except (ValueError, RuntimeError) as exc:
                ui.error(f"Index failed: {exc}")
                continue

            ui.success("Index completed")
            print(f"  Source      : {source}")
            print(f"  Resolved    : {repo_path}")
            print(f"  Output      : {graph_path}")
            print(f"  Scanned     : {result.scanned_files}")
            print(f"  Indexed     : {result.indexed_files}")
            print(f"  Nodes/Edges : {stats['nodes']} / {stats['edges']}")
            continue

        if cmd == "load":
            candidate = Path(rest[0]).resolve() if rest else graph_path
            if not candidate.exists():
                ui.error(f"Graph file not found: {candidate}")
                continue
            loaded_graph = GraphStore.from_json(candidate)
            graph_path = candidate
            ui.success(f"Loaded graph: {graph_path}")
            continue

        if loaded_graph is None:
            ui.warn("No graph loaded. Run 'index <repo-or-github-url>' or 'load [PATH]' first.")
            continue

        if cmd == "stats":
            stats = loaded_graph.stats()
            if raw_mode:
                _print_json(stats)
            else:
                _render_stats_panel(stats, ui)
            continue

        if cmd == "find":
            if not rest:
                ui.warn("Usage: find <name> [--limit N]")
                continue
            limit = 20
            if "--limit" in rest:
                try:
                    limit = int(rest[rest.index("--limit") + 1])
                except (IndexError, ValueError):
                    ui.warn("Usage: find <name> [--limit N]")
                    continue
            name = rest[0]
            rows = find_symbol(loaded_graph, name, limit=limit)
            if raw_mode:
                _print_json(rows)
            else:
                _render_table(
                    title=f"Find Results ({len(rows)})",
                    rows=rows,
                    columns=[("type", "TYPE"), ("name", "NAME"), ("id", "ID"), ("file", "FILE")],
                    ui=ui,
                )
            continue

        if cmd == "callers":
            if not rest:
                ui.warn("Usage: callers <symbol> [--limit N]")
                continue
            limit = 50
            if "--limit" in rest:
                try:
                    limit = int(rest[rest.index("--limit") + 1])
                except (IndexError, ValueError):
                    ui.warn("Usage: callers <symbol> [--limit N]")
                    continue
            symbol = rest[0]
            rows = callers_of(loaded_graph, symbol, limit=limit)
            if raw_mode:
                _print_json(rows)
            else:
                _render_table(
                    title=f"Callers ({len(rows)})",
                    rows=rows,
                    columns=[("caller_name", "CALLER"), ("caller", "CALLER_ID"), ("line", "LINE"), ("confidence", "CONF")],
                    ui=ui,
                )
            continue

        if cmd == "related":
            if not rest:
                ui.warn("Usage: related <file> [--depth N] [--limit N]")
                continue
            depth = 2
            limit = 100
            if "--depth" in rest:
                try:
                    depth = int(rest[rest.index("--depth") + 1])
                except (IndexError, ValueError):
                    ui.warn("Usage: related <file> [--depth N] [--limit N]")
                    continue
            if "--limit" in rest:
                try:
                    limit = int(rest[rest.index("--limit") + 1])
                except (IndexError, ValueError):
                    ui.warn("Usage: related <file> [--depth N] [--limit N]")
                    continue
            rows = [{"file": p} for p in related_files(loaded_graph, rest[0], depth=depth, limit=limit)]
            if raw_mode:
                _print_json([row["file"] for row in rows])
            else:
                _render_table(
                    title=f"Related Files ({len(rows)})",
                    rows=rows,
                    columns=[("file", "FILE")],
                    ui=ui,
                )
            continue

        if cmd == "path":
            if len(rest) < 2:
                ui.warn("Usage: path <from> <to> [--max-depth N]")
                continue
            source = rest[0]
            target = rest[1]
            max_depth = 12
            if "--max-depth" in rest:
                try:
                    max_depth = int(rest[rest.index("--max-depth") + 1])
                except (IndexError, ValueError):
                    ui.warn("Usage: path <from> <to> [--max-depth N]")
                    continue

            rows = shortest_path(loaded_graph, source, target, max_depth=max_depth)
            if raw_mode:
                _print_json(rows)
            else:
                _render_table(
                    title=f"Path ({len(rows)} steps)",
                    rows=rows,
                    columns=[("step", "STEP"), ("edge", "EDGE"), ("type", "TYPE"), ("name", "NAME"), ("id", "ID")],
                    ui=ui,
                )
            continue

        if cmd == "impact":
            if not rest:
                ui.warn("Usage: impact <symbol> [--depth N] [--limit N]")
                continue
            depth = 3
            limit = 200
            if "--depth" in rest:
                try:
                    depth = int(rest[rest.index("--depth") + 1])
                except (IndexError, ValueError):
                    ui.warn("Usage: impact <symbol> [--depth N] [--limit N]")
                    continue
            if "--limit" in rest:
                try:
                    limit = int(rest[rest.index("--limit") + 1])
                except (IndexError, ValueError):
                    ui.warn("Usage: impact <symbol> [--depth N] [--limit N]")
                    continue

            rows = impact_of(loaded_graph, rest[0], depth=depth, limit=limit)
            if raw_mode:
                _print_json(rows)
            else:
                _render_table(
                    title=f"Blast Radius ({len(rows)})",
                    rows=rows,
                    columns=[("distance", "DIST"), ("via", "VIA"), ("type", "TYPE"), ("name", "NAME"), ("file", "FILE")],
                    ui=ui,
                )
            continue

        if cmd == "export":
            if not rest:
                ui.warn("Usage: export graphml [--out PATH] | export neo4j [--out DIR]")
                continue
            format_name = rest[0].lower()
            if format_name == "graphml":
                out = Path("tmp") / "code-atlas.graphml"
                if "--out" in rest:
                    try:
                        out = Path(rest[rest.index("--out") + 1])
                    except IndexError:
                        ui.warn("Usage: export graphml [--out PATH]")
                        continue
                out = out.resolve()
                path = export_graphml(loaded_graph, out)
                ui.success(f"GraphML exported: {path}")
                continue
            if format_name == "neo4j":
                out_dir = Path("tmp") / "neo4j"
                if "--out" in rest:
                    try:
                        out_dir = Path(rest[rest.index("--out") + 1])
                    except IndexError:
                        ui.warn("Usage: export neo4j [--out DIR]")
                        continue
                out_dir = out_dir.resolve()
                nodes_csv, edges_csv = export_neo4j_csv(loaded_graph, out_dir)
                ui.success(f"Neo4j CSV exported: {nodes_csv} and {edges_csv}")
                continue
            ui.warn("Unknown export format. Use 'graphml' or 'neo4j'.")
            continue

        if cmd == "visual":
            if not rest:
                ui.warn("Usage: visual <symbol> [--depth N] [--limit N] [--out PATH]")
                continue
            symbol = rest[0]
            depth = 2
            limit = 120
            out = Path("tmp") / "graph-view.html"

            if "--depth" in rest:
                try:
                    depth = int(rest[rest.index("--depth") + 1])
                except (IndexError, ValueError):
                    ui.warn("Usage: visual <symbol> [--depth N] [--limit N] [--out PATH]")
                    continue
            if "--limit" in rest:
                try:
                    limit = int(rest[rest.index("--limit") + 1])
                except (IndexError, ValueError):
                    ui.warn("Usage: visual <symbol> [--depth N] [--limit N] [--out PATH]")
                    continue
            if "--out" in rest:
                try:
                    out = Path(rest[rest.index("--out") + 1])
                except IndexError:
                    ui.warn("Usage: visual <symbol> [--depth N] [--limit N] [--out PATH]")
                    continue

            html_path = build_visual_html(
                loaded_graph,
                symbol,
                out.resolve(),
                depth=depth,
                limit=limit,
                open_browser=True,
            )
            ui.success(f"Opened interactive graph: {html_path}")
            continue

        ui.warn("Unknown command. Type 'help' for usage.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="code-atlas",
        description="Interactive knowledge graph CLI for AI code exploration.",
    )
    parser.add_argument("--graph", default=str(DEFAULT_GRAPH_RELATIVE), help="Graph JSON path to preload")
    parser.set_defaults(func=_cmd_interactive)

    return parser


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
