from __future__ import annotations

import argparse
import shlex
from pathlib import Path

from .commands import ShellState, cmd_callers, cmd_find, cmd_impact, cmd_index, cmd_load, cmd_path, cmd_related, cmd_stats, cmd_where
from .extra_commands import cmd_export, cmd_visual
from .help import interactive_help
from .ui import ASCII_LOGO, UI, clear_screen
from ..graph import GraphStore


DEFAULT_GRAPH_RELATIVE = Path("tmp") / "code-atlas.graph.json"


def run_shell(graph_path: Path) -> int:
    ui = UI()
    state = ShellState(ui=ui, graph_path=graph_path, loaded_graph=GraphStore.from_json(graph_path) if graph_path.exists() else None)
    print(ui.c(ASCII_LOGO, ui.CYAN + ui.BOLD))
    ui.header("Code Atlas Interactive")
    ui.muted("Type 'help' for commands, 'exit' to quit.")

    while True:
        prompt = ui.c("atlas", ui.BOLD + ui.CYAN) + ui.c(f"[{state.graph_path.name if state.loaded_graph else 'no-graph'}]", ui.DIM) + ui.c(" > ", ui.BOLD)
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

        cmd, rest = parts[0].lower(), parts[1:]
        if cmd in {"exit", "quit"}:
            ui.success("Goodbye.")
            return 0
        if cmd == "help":
            print(interactive_help())
        elif cmd == "clear":
            clear_screen()
            print(ui.c(ASCII_LOGO, ui.CYAN + ui.BOLD))
            ui.header("Code Atlas Interactive")
            ui.muted("Type 'help' for commands, 'exit' to quit.")
        elif cmd == "raw":
            if rest and rest[0] in {"on", "off"}:
                state.raw_mode = rest[0] == "on"
                ui.success(f"Raw JSON output: {'enabled' if state.raw_mode else 'disabled'}")
            else:
                ui.warn("Usage: raw on|off")
        elif cmd == "where":
            cmd_where(state)
        elif cmd == "index":
            cmd_index(state, rest)
        elif cmd == "load":
            cmd_load(state, rest)
        elif cmd == "stats":
            cmd_stats(state)
        elif cmd == "find":
            cmd_find(state, rest)
        elif cmd == "callers":
            cmd_callers(state, rest)
        elif cmd == "related":
            cmd_related(state, rest)
        elif cmd == "path":
            cmd_path(state, rest)
        elif cmd == "impact":
            cmd_impact(state, rest)
        elif cmd == "export":
            cmd_export(state, rest)
        elif cmd == "visual":
            cmd_visual(state, rest)
        else:
            ui.warn("Unknown command. Type 'help' for usage.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="code-atlas", description="Interactive knowledge graph CLI for AI code exploration.")
    parser.add_argument("--graph", default=str(DEFAULT_GRAPH_RELATIVE), help="Graph JSON path to preload")
    return parser


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_shell(Path(args.graph).resolve())
