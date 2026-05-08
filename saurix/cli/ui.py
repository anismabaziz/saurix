from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

from rich.console import Console
from rich.json import JSON
from rich.text import Text


ASCII_LOGO = r"""
   ______          __        ___   __  __
  / ____/___  ____/ /__     /   | / /_/ /___ ______
 / /   / __ \/ __  / _ \   / /| |/ __/ / __ `/ ___/
/ /___/ /_/ / /_/ /  __/  / ___ / /_/ / /_/ (__  )
\____/\____/\__,_/\___/  /_/  |_\__/_/\__,_/____/
"""


class UI:
    BOLD = "bold"
    DIM = "dim"
    BLUE = "blue"
    CYAN = "cyan"
    def __init__(
        self,
        console: Console | None = None,
        sink: Callable[[Any], None] | None = None,
        allow_blocking_input: bool = True,
    ) -> None:
        self.console = console or Console()
        self._sink = sink
        self.allow_blocking_input = allow_blocking_input
        self._progress_active = False
        self._last_progress_message = ""

    def set_sink(self, sink: Callable[[Any], None] | None) -> None:
        self._sink = sink

    def c(self, text: str, style: str) -> str:
        return f"[{style}]{text}[/]"

    def prompt(self, graph_name: str) -> str:
        parts = [
            self.c("atlas", "bold cyan"),
            self.c(f"[{graph_name}]", "dim"),
            self.c(" > ", "bold"),
        ]
        return "".join(parts)

    def print(self, text: Any = "") -> None:
        self._flush_progress_line_before_print()
        if self._sink is not None:
            self._sink(text)
            return
        self.console.print(text)

    def header(self, text: str) -> None:
        self.print(Text(text, style="bold cyan"))

    def info(self, text: str) -> None:
        self.print(Text(text, style="bright_blue"))

    def success(self, text: str) -> None:
        self.print(Text(text, style="bold green"))

    def warn(self, text: str) -> None:
        self.print(Text(text, style="bold yellow"))

    def error(self, text: str) -> None:
        self.print(Text(text, style="bold red"))

    def muted(self, text: str) -> None:
        self.print(Text(text, style="dim"))

    def progress_line_start(self, message: str) -> None:
        if self._sink is not None:
            self._sink(Text(message, style="dim"))
            return
        self._progress_active = True
        self._last_progress_message = message
        self._write_progress_line(message)

    def progress_line_update(self, completed: int, total: int, label: str = "") -> None:
        pct = int((completed / total) * 100) if total > 0 else 100
        if label:
            message = f"Indexing files... {completed}/{total} ({pct}%) {label}"
        else:
            message = f"Indexing files... {completed}/{total} ({pct}%)"
        if self._sink is not None:
            self._sink(Text(message, style="dim"))
            return
        self._progress_active = True
        self._last_progress_message = message
        self._write_progress_line(message)

    def progress_line_finish(self, message: str | None = None) -> None:
        final_message = message or self._last_progress_message or "Done"
        if self._sink is not None:
            self._sink(Text(final_message, style="dim"))
            return
        if self._progress_active:
            self._write_progress_line(final_message)
            self.console.file.write("\n")
            self.console.file.flush()
        self._progress_active = False
        self._last_progress_message = ""

    def _write_progress_line(self, message: str) -> None:
        width = max(self.console.width - 1, 20)
        clipped = message[:width]
        padded = clipped.ljust(width)
        self.console.file.write("\r" + padded)
        self.console.file.flush()

    def _flush_progress_line_before_print(self) -> None:
        if self._sink is not None:
            return
        if self._progress_active:
            self.console.file.write("\n")
            self.console.file.flush()
            self._progress_active = False


def print_json(payload: object, ui: UI | None = None) -> None:
    rendered = JSON.from_data(payload)
    if ui is not None:
        ui.print(rendered)
        return
    Console().print_json(data=json.dumps(payload))


def clear_screen() -> None:
    Console().clear()
