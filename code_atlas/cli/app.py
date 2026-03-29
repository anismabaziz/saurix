from __future__ import annotations

"""Interactive shell entrypoint and command dispatch loop."""

import argparse
import shlex
from collections.abc import Callable
from pathlib import Path

from .ask_commands import cmd_ask
from .ai_settings import cmd_models, cmd_providers, cmd_set_key, cmd_set_model, cmd_set_provider
from .commands import ShellState, cmd_callers, cmd_find, cmd_impact, cmd_index, cmd_load, cmd_path, cmd_related, cmd_stats, cmd_where
from .extra_commands import cmd_export, cmd_visual
from .help import interactive_help
from .ui import ASCII_LOGO, UI, clear_screen
from ..graph import GraphStore


DEFAULT_GRAPH_RELATIVE = Path("tmp") / "code-atlas.graph.json"


def _render_banner(ui: UI, provider: str) -> None:
    ui.print(ui.c(ASCII_LOGO, "bold cyan"))
    ui.header("Code Atlas Interactive")
    ui.muted(f"Type 'help' for commands, 'exit' to quit. AI provider: {provider}")


def create_state(graph_path: Path, provider: str, model: str | None, ui: UI) -> ShellState:
    return ShellState(
        ui=ui,
        graph_path=graph_path,
        loaded_graph=GraphStore.from_json(graph_path) if graph_path.exists() else None,
        provider=provider,
        model=model,
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
            _render_banner(ui, state.provider)
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
    elif cmd == "ask":
        cmd_ask(state, rest, provider=state.provider, model=state.model)
    elif cmd == "set-key":
        cmd_set_key(state, rest)
    elif cmd == "set-provider":
        cmd_set_provider(state, rest)
        ui.muted(f"Active AI provider: {state.provider}")
    elif cmd == "set-model":
        cmd_set_model(state, rest)
    elif cmd == "providers":
        cmd_providers(state)
    elif cmd == "models":
        cmd_models(state, rest)
    elif cmd == "export":
        cmd_export(state, rest)
    elif cmd == "visual":
        cmd_visual(state, rest)
    else:
        ui.warn("Unknown command. Type 'help' for usage.")
    return True


def run_shell(graph_path: Path, provider: str, model: str | None) -> int:
    """Start the REPL, keep shared shell state, and route user commands."""
    ui = UI()
    state = create_state(graph_path, provider, model, ui)
    _render_banner(ui, state.provider)

    while True:
        prompt = ui.c("atlas", ui.BOLD + ui.CYAN)
        prompt += ui.c(f"<{state.provider}>", "blue")
        prompt += ui.c(f"[{state.graph_path.name if state.loaded_graph else 'no-graph'}]", "dim")
        prompt += ui.c(" > ", "bold")
        try:
            ui.console.print(prompt, end="")
            raw = input().strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not dispatch_command(state, raw):
            return 0


def build_parser() -> argparse.ArgumentParser:
    """Build startup parser for one-command interactive mode."""
    parser = argparse.ArgumentParser(prog="code-atlas", description="Interactive knowledge graph CLI for AI code exploration.")
    parser.add_argument("--graph", default=str(DEFAULT_GRAPH_RELATIVE), help="Graph JSON path to preload")
    parser.add_argument("--provider", choices=["openai", "anthropic", "google"], default="google", help="LLM provider for ask command")
    parser.add_argument("--model", default=None, help="Optional model override for provider")
    parser.add_argument("--tui", action="store_true", help="Launch full-screen Textual mode")
    return parser


def run(argv: list[str] | None = None) -> int:
    """CLI public entrypoint used by main.py and project scripts."""
    args = build_parser().parse_args(argv)
    if args.tui:
        try:
            from .tui import run_tui

            return run_tui(Path(args.graph).resolve(), args.provider, args.model)
        except Exception:
            return run_shell(Path(args.graph).resolve(), args.provider, args.model)
    return run_shell(Path(args.graph).resolve(), args.provider, args.model)
