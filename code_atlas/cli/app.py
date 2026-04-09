from __future__ import annotations

"""Interactive CLI entrypoint and command dispatch."""

import argparse
import shlex
from collections.abc import Callable
from pathlib import Path

from .commands import ShellState, cmd_callers, cmd_find, cmd_impact, cmd_index, cmd_load, cmd_path, cmd_related, cmd_stats, cmd_where
from .extra_commands import cmd_export, cmd_visual, cmd_visual_all
from .help import interactive_help
from .ui import ASCII_LOGO, UI, clear_screen
from ..graph import GraphStore


DEFAULT_GRAPH_RELATIVE = Path("tmp") / "code-atlas.graph.json"


def create_state(graph_path: Path, ui: UI) -> ShellState:
    return ShellState(
        ui=ui,
        graph_path=graph_path,
        loaded_graph=GraphStore.from_json(graph_path) if graph_path.exists() else None,
    )


def dispatch_command(state: ShellState, raw: str, on_clear: Callable[[], None] | None = None) -> bool:
    """Run one interactive command. Returns False when shell should exit."""
    ui = state.ui
    if not raw.strip():
        return True

    try:
        parts = shlex.split(raw)
    except ValueError as exc:
        ui.error(f"Parse error: {exc}")
        return True

    cmd, rest = parts[0].lower(), parts[1:]
    if cmd in {"exit", "quit"}:
        ui.success("Goodbye.")
        return False
    if cmd == "help":
        ui.print(interactive_help())
    elif cmd == "clear":
        if on_clear is not None:
            on_clear()
        else:
            clear_screen()
            _render_banner(ui)
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
    elif cmd == "visual-all":
        cmd_visual_all(state, rest)
    else:
        ui.warn("Unknown command. Type 'help' for usage.")
    return True


def build_parser() -> argparse.ArgumentParser:
    """Build startup parser for interactive terminal mode."""
    parser = argparse.ArgumentParser(prog="code-atlas", description="Knowledge graph CLI for AI code exploration.")
    parser.add_argument("--graph", default=str(DEFAULT_GRAPH_RELATIVE), help="Graph JSON path to preload")
    return parser


def run(argv: list[str] | None = None) -> int:
    """CLI public entrypoint used by main.py and project scripts."""
    args = build_parser().parse_args(argv)
    ui = UI()
    graph_path = Path(args.graph).resolve()
    state = create_state(graph_path, ui)
    _render_banner(ui)

    while True:
        graph_name = state.graph_path.name if state.loaded_graph else "no-graph"
        try:
            raw = ui.console.input(ui.prompt(graph_name))
        except (EOFError, KeyboardInterrupt):
            ui.print()
            ui.success("Goodbye.")
            return 0

        if not dispatch_command(state, raw):
            return 0


def _render_banner(ui: UI) -> None:
    ui.print(f"[bold cyan]{ASCII_LOGO}[/]")
    ui.header("Code Atlas Interactive")
    ui.muted("Type 'help' to list commands.")
