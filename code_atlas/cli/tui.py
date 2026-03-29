from __future__ import annotations

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

    def compose(self) -> ComposeResult:
        with Container(id="body"):
            yield RichLog(id="output", highlight=True, markup=True, wrap=True, auto_scroll=False)
        yield Input(placeholder="Type command (help, index, find, ask, stats, visual, quit)...", id="command")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Code Atlas"
        self.sub_title = "Modern interactive shell"
        self._show_welcome()
        self.query_one("#command", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        event.input.value = ""
        if not raw:
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

def run_tui(graph_path: Path, provider: str, model: str | None) -> int:
    app = AtlasTUI(graph_path=graph_path, provider=provider, model=model)
    app.run()
    return 0
