from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path

from .graph import GraphStore
from .indexer import build_graph
from .query import callers_of, find_symbol, related_files
from .repo_source import prepare_repo_source


ASCII_LOGO = r"""
   ______          __        ___   __  __
  / ____/___  ____/ /__     /   | / /_/ /___ ______
 / /   / __ \/ __  / _ \   / /| |/ __/ / __ `/ ___/
/ /___/ /_/ / /_/ /  __/  / ___ / /_/ / /_/ (__  )
\____/\____/\__,_/\___/  /_/  |_\__/_/\__,_/____/
"""


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _cmd_index(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    out = Path(args.out).resolve()

    result = build_graph(repo)
    result.graph.write_json(out)
    stats = result.graph.stats()

    print(f"Indexed repo: {repo}")
    print(f"Scanned files: {result.scanned_files}")
    print(f"Indexed files: {result.indexed_files}")
    print(f"Nodes: {stats['nodes']} | Edges: {stats['edges']}")
    print(f"Graph written to: {out}")
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    graph = GraphStore.from_json(Path(args.graph).resolve())
    stats = graph.stats()
    _print_json(stats)
    return 0


def _cmd_find_symbol(args: argparse.Namespace) -> int:
    graph = GraphStore.from_json(Path(args.graph).resolve())
    rows = find_symbol(graph, args.name, limit=args.limit)
    _print_json(rows)
    return 0


def _cmd_callers(args: argparse.Namespace) -> int:
    graph = GraphStore.from_json(Path(args.graph).resolve())
    rows = callers_of(graph, args.symbol, limit=args.limit)
    _print_json(rows)
    return 0


def _cmd_related(args: argparse.Namespace) -> int:
    graph = GraphStore.from_json(Path(args.graph).resolve())
    rows = related_files(graph, args.file, depth=args.depth, limit=args.limit)
    _print_json(rows)
    return 0


def _interactive_help() -> str:
    return "\n".join(
        [
            "Interactive commands:",
            "  help                                   Show this message",
            "  index <repo-or-github-url> [--out PATH] Index source to graph JSON",
            "  load [PATH]                            Load a graph JSON file",
            "  stats                                  Show graph statistics",
            "  find <name> [--limit N]                Find symbol by fuzzy name",
            "  callers <symbol> [--limit N]           Show callers of a symbol",
            "  related <file> [--depth N] [--limit N] Show related files",
            "  where                                  Show currently loaded graph",
            "  exit | quit                            Leave interactive mode",
        ]
    )


def _cmd_interactive(args: argparse.Namespace) -> int:
    graph_path = Path(getattr(args, "graph", "code-atlas.graph.json")).resolve()
    loaded_graph: GraphStore | None = None

    if graph_path.exists():
        loaded_graph = GraphStore.from_json(graph_path)

    print(ASCII_LOGO)
    print("Code Atlas interactive mode")
    print("Type 'help' for commands, 'exit' to quit.")

    while True:
        prompt = f"code-atlas[{graph_path.name if loaded_graph else 'no-graph'}]> "
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
            print(f"Parse error: {exc}")
            continue

        cmd = parts[0].lower()
        rest = parts[1:]

        if cmd in {"exit", "quit"}:
            return 0

        if cmd == "help":
            print(_interactive_help())
            continue

        if cmd == "where":
            if loaded_graph:
                print(f"Loaded graph: {graph_path}")
            else:
                print("No graph loaded")
            continue

        if cmd == "index":
            if not rest:
                print("Usage: index <repo-or-github-url> [--out PATH]")
                continue
            out = graph_path
            source = rest[0]

            if "--out" in rest:
                try:
                    out = Path(rest[rest.index("--out") + 1]).resolve()
                except IndexError:
                    print("Usage: index <repo-or-github-url> [--out PATH]")
                    continue

            try:
                with prepare_repo_source(source) as (repo_path, source_kind):
                    print(f"Preparing source: {source_kind}")
                    result = build_graph(repo_path)
                    result.graph.write_json(out)
                    graph_path = out
                    loaded_graph = result.graph
                    stats = result.graph.stats()
            except (ValueError, RuntimeError) as exc:
                print(f"Index failed: {exc}")
                continue

            print(f"Indexed source: {source}")
            print(f"Resolved path: {repo_path}")
            print(f"Scanned files: {result.scanned_files}")
            print(f"Indexed files: {result.indexed_files}")
            print(f"Nodes: {stats['nodes']} | Edges: {stats['edges']}")
            continue

        if cmd == "load":
            candidate = Path(rest[0]).resolve() if rest else graph_path
            if not candidate.exists():
                print(f"Graph file not found: {candidate}")
                continue
            loaded_graph = GraphStore.from_json(candidate)
            graph_path = candidate
            print(f"Loaded graph: {graph_path}")
            continue

        if loaded_graph is None:
            print("No graph loaded. Run 'index <repo>' or 'load [PATH]' first.")
            continue

        if cmd == "stats":
            _print_json(loaded_graph.stats())
            continue

        if cmd == "find":
            if not rest:
                print("Usage: find <name> [--limit N]")
                continue
            limit = 20
            if "--limit" in rest:
                try:
                    limit = int(rest[rest.index("--limit") + 1])
                except (IndexError, ValueError):
                    print("Usage: find <name> [--limit N]")
                    continue
            name = rest[0]
            _print_json(find_symbol(loaded_graph, name, limit=limit))
            continue

        if cmd == "callers":
            if not rest:
                print("Usage: callers <symbol> [--limit N]")
                continue
            limit = 50
            if "--limit" in rest:
                try:
                    limit = int(rest[rest.index("--limit") + 1])
                except (IndexError, ValueError):
                    print("Usage: callers <symbol> [--limit N]")
                    continue
            symbol = rest[0]
            _print_json(callers_of(loaded_graph, symbol, limit=limit))
            continue

        if cmd == "related":
            if not rest:
                print("Usage: related <file> [--depth N] [--limit N]")
                continue
            depth = 2
            limit = 100
            if "--depth" in rest:
                try:
                    depth = int(rest[rest.index("--depth") + 1])
                except (IndexError, ValueError):
                    print("Usage: related <file> [--depth N] [--limit N]")
                    continue
            if "--limit" in rest:
                try:
                    limit = int(rest[rest.index("--limit") + 1])
                except (IndexError, ValueError):
                    print("Usage: related <file> [--depth N] [--limit N]")
                    continue
            _print_json(related_files(loaded_graph, rest[0], depth=depth, limit=limit))
            continue

        print("Unknown command. Type 'help' for usage.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="code-atlas",
        description="Interactive knowledge graph CLI for AI code exploration.",
    )
    parser.add_argument("--graph", default="code-atlas.graph.json", help="Graph JSON path to preload")
    parser.set_defaults(func=_cmd_interactive)

    return parser


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
