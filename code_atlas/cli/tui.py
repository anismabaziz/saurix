from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Footer, Input, RichLog

from .app import create_state, dispatch_command
from .ui import ASCII_LOGO, UI
from ..llm.client import DEFAULTS
from ..llm.keychain import save_api_key


class AtlasTUI(App[None]):
    CSS = """
    Screen {
        layout: vertical;
        background: #020617;
        color: #e2e8f0;
    }

    Footer {
        background: #0f172a;
        color: #94a3b8;
    }

    #body {
        layout: vertical;
        height: 1fr;
        padding: 0 1;
    }

    #output {
        height: 1fr;
        min-height: 8;
        border: round #0ea5e9;
        background: #030b1a;
        padding: 0 1;
    }

    #command {
        dock: bottom;
        margin: 0 1 1 1;
        border: round #22d3ee;
        background: #0b1220;
        color: #e2e8f0;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear_output", "Clear Output"),
    ]

    def __init__(self, graph_path: Path, provider: str, model: str | None) -> None:
        super().__init__()
        self._graph_path = graph_path
        self._provider = provider
        self._model = model
        self._ui = UI(sink=self._emit, allow_blocking_input=False)
        self._state = create_state(graph_path, provider, model, self._ui)
        self._onboarding_step: str | None = "ask_enable"

    def compose(self) -> ComposeResult:
        with Container(id="body"):
            yield RichLog(id="output", highlight=True, markup=True, wrap=True, auto_scroll=False)
        yield Input(placeholder="Type command (help, ai-status, index, find, ask, stats, visual, quit)...", id="command")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Code Atlas"
        self.sub_title = "Modern interactive shell"
        self._show_onboarding_prompt()
        self.query_one("#command", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        event.input.value = ""
        if not raw:
            return

        if self._onboarding_step is not None:
            self._handle_onboarding_input(raw)
            return

        output = self.query_one("#output", RichLog)
        output.clear()
        output.write(Text(f"> {raw}", style="bold cyan"))
        output.write(Text("running...", style="dim"))

        prompt = Text.assemble(
            ("atlas", "bold cyan"),
            (f"<{self._state.provider}>", "bright_blue"),
            (f"[{self._state.graph_path.name if self._state.loaded_graph else 'no-graph'}]", "dim"),
            (" > ", "bold"),
            (raw, "white"),
        )
        lines: list[Any] = []
        self._ui.set_sink(lines.append)
        try:
            keep_running = dispatch_command(self._state, raw, on_clear=self._clear_and_redraw)
            if keep_running:
                body: Any = Group(prompt, Text(""), *(lines or [Text("No output", style="dim")]))
            else:
                body = Group(prompt, Text(""), *lines)
        finally:
            self._ui.set_sink(self._emit)

        output.clear()
        output.write(Panel(body, title="Command Result", border_style="cyan"))
        output.scroll_home(animate=False)

        if not keep_running:
            self.exit()

    def action_clear_output(self) -> None:
        self._clear_and_redraw()

    def _emit(self, renderable: object) -> None:
        output = self.query_one("#output", RichLog)
        output.clear()
        output.write(renderable)
        output.scroll_home(animate=False)

    def _clear_and_redraw(self) -> None:
        self._show_welcome()

    def _show_welcome(self) -> None:
        self._emit(
            Panel(
                Text.from_markup(
                    f"[bold cyan]{ASCII_LOGO}[/]\n[bold white]Code Atlas Interactive[/]\n[dim]Type a command and press Enter. Output is replaced each run.[/]"
                ),
                border_style="cyan",
                title="Command Result",
            )
        )

    def _show_onboarding_prompt(self) -> None:
        if self._onboarding_step == "ask_enable":
            text = (
                f"[bold cyan]{ASCII_LOGO}[/]\n"
                "[bold white]Welcome to Code Atlas[/]\n\n"
                "Enable AI features now? [bold cyan](yes/no)[/]\n"
                "If yes, you will choose provider, model, and API key."
            )
            self._emit(Panel(Text.from_markup(text), title="Startup Setup", border_style="cyan"))
            return

        if self._onboarding_step == "provider":
            options = ", ".join(sorted(DEFAULTS.keys()))
            self._emit(
                Panel(
                    Text.from_markup(
                        f"[bold white]Choose AI provider:[/] {options}\n"
                        f"Current default: [cyan]{self._state.provider}[/]"
                    ),
                    title="Startup Setup",
                    border_style="cyan",
                )
            )
            return

        if self._onboarding_step == "model":
            provider = self._state.provider
            default_model = DEFAULTS[provider].model
            suggested = ", ".join(_provider_models(provider))
            self._emit(
                Panel(
                    Text.from_markup(
                        f"[bold white]Choose model for {provider}[/]\n"
                        f"Suggested: {suggested}\n"
                        f"Press Enter or type [cyan]default[/] to use: [cyan]{default_model}[/]"
                    ),
                    title="Startup Setup",
                    border_style="cyan",
                )
            )
            return

        if self._onboarding_step == "key":
            env_name = DEFAULTS[self._state.provider].api_key_env
            self._emit(
                Panel(
                    Text.from_markup(
                        f"[bold white]Paste API key for {self._state.provider}[/]\n"
                        f"It will be set for this session as [cyan]{env_name}[/].\n"
                        "Type [cyan]skip[/] to continue without setting a key now."
                    ),
                    title="Startup Setup",
                    border_style="cyan",
                )
            )

    def _handle_onboarding_input(self, raw: str) -> None:
        normalized = raw.strip().lower()

        if self._onboarding_step == "ask_enable":
            if normalized in {"no", "n", "skip"}:
                self._onboarding_step = None
                self._show_welcome()
                return
            if normalized in {"yes", "y"}:
                self._onboarding_step = "provider"
                self._show_onboarding_prompt()
                return
            self._emit(Panel(Text("Please type yes or no.", style="yellow"), title="Startup Setup", border_style="yellow"))
            return

        if self._onboarding_step == "provider":
            if normalized not in DEFAULTS:
                self._emit(
                    Panel(
                        Text(f"Unknown provider '{raw}'. Use: {', '.join(sorted(DEFAULTS))}", style="yellow"),
                        title="Startup Setup",
                        border_style="yellow",
                    )
                )
                return
            self._state.provider = normalized
            self._onboarding_step = "model"
            self._show_onboarding_prompt()
            return

        if self._onboarding_step == "model":
            if normalized in {"", "default"}:
                self._state.model = None
            else:
                self._state.model = raw.strip()
            self._onboarding_step = "key"
            self._show_onboarding_prompt()
            return

        if self._onboarding_step == "key":
            if normalized != "skip" and raw.strip():
                env_name = DEFAULTS[self._state.provider].api_key_env
                key_value = raw.strip()
                os.environ[env_name] = key_value
                save_api_key(self._state.provider, key_value)
            self._onboarding_step = None
            self._show_welcome()


def _provider_models(provider: str) -> list[str]:
    if provider == "openai":
        return ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1", "o4-mini"]
    if provider == "anthropic":
        return ["claude-3-5-haiku-latest", "claude-3-5-sonnet-latest", "claude-3-7-sonnet-latest"]
    return ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]

def run_tui(graph_path: Path, provider: str, model: str | None) -> int:
    app = AtlasTUI(graph_path=graph_path, provider=provider, model=model)
    app.run()
    return 0
