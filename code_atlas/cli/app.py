from __future__ import annotations

"""
CLI Application Shell

This module implements the interactive REPL (Read-Eval-Print Loop) for Code Atlas.
It handles user input, parses commands using shlex (to support quoted paths/names),
and dispatches them to their respective implementations in commands.py and extra_commands.py.
"""

import argparse
import shlex
from collections.abc import Callable
from pathlib import Path

from .commands import ShellState, cmd_callers, cmd_find, cmd_impact, cmd_index, cmd_load, cmd_path, cmd_related, cmd_stats, cmd_where
from .extra_commands import cmd_export, cmd_visual
from .help import interactive_help
from .ui import ASCII_LOGO, UI, clear_screen
from ..core.graph import GraphStore
from ..infra.config import config


# Default location for the graph file, pulled from centralized config
DEFAULT_GRAPH_RELATIVE = config.default_graph_path


def create_state(graph_path: Path, ui: UI) -> ShellState:
    """Initializes the persistent state for the interactive session."""
    return ShellState(
        ui=ui,
        graph_path=graph_path,
        loaded_graph=GraphStore.from_json(graph_path) if graph_path.exists() else None,
    )


def dispatch_command(state: ShellState, raw: str, on_clear: Callable[[], None] | None = None) -> bool:
    """
    Parses and executes a single user command.
    
    Returns:
        False if the shell should exit (e.g., 'exit' command), True otherwise.
    """
    ui = state.ui
    if not raw.strip():
        return True

    try:
        # shlex.split allows commands like: find "My Class Name"
        parts = shlex.split(raw)
    except ValueError as exc:
        ui.error(f"Parse error: {exc}")
        return True

    cmd, rest = parts[0].lower(), parts[1:]
    
    # Built-in shell control commands
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
        # Toggle raw JSON output for all subsequent commands
        if rest and rest[0] in {"on", "off"}:
            state.raw_mode = rest[0] == "on"
            ui.success(f"Raw JSON output: {'enabled' if state.raw_mode else 'disabled'}")
        else:
            ui.warn("Usage: raw on|off")
            
    # Core domain commands (delegated to commands.py)
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
        
    # Extra commands (delegated to extra_commands.py)
    elif cmd == "export":
        cmd_export(state, rest)
    elif cmd == "visual":
        cmd_visual(state, rest)
    else:
        ui.warn("Unknown command. Type 'help' for usage.")
        
    return True


def build_parser() -> argparse.ArgumentParser:
    """Configures the command-line argument parser for the atlas entrypoint."""
    parser = argparse.ArgumentParser(prog="code-atlas", description="Knowledge graph CLI for AI code exploration.")
    parser.add_argument("--graph", default=str(DEFAULT_GRAPH_RELATIVE), help="Graph JSON path to preload")
    return parser


def run(argv: list[str] | None = None) -> int:
    """
    Main loop for the interactive shell.
    
    Handles preloading of graphs, the interactive input prompt, 
    and graceful shutdowns on Ctrl+C or EOF.
    """
    args = build_parser().parse_args(argv)
    ui = UI()
    graph_path = Path(args.graph).resolve()
    state = create_state(graph_path, ui)
    
    _render_banner(ui)

    while True:
        # Dynamic prompt showing the currently loaded graph file
        graph_name = state.graph_path.name if state.loaded_graph else "no-graph"
        try:
            raw = ui.console.input(ui.prompt(graph_name))
        except (EOFError, KeyboardInterrupt):
            ui.print()
            ui.success("Goodbye.")
            return 0

        # Dispatch the command and check if we should exit
        if not dispatch_command(state, raw):
            return 0


def _render_banner(ui: UI) -> None:
    """Displays the Code Atlas ASCII logo and initialization message."""
    ui.print(f"[bold cyan]{ASCII_LOGO}[/]")
    ui.header("Code Atlas Interactive")
    ui.muted("Type 'help' to list commands.")
