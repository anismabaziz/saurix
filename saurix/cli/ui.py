from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from rich.console import Console
from rich.json import JSON
from rich.panel import Panel
from rich.table import Table
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


def interactive_help() -> str:
    return "\n".join(
        [
            "Interactive commands:",
            "  help                                        Show this message",
            "  index <repo-or-github-url> [--out PATH] [--exclude dir1,dir2]",
            "                                              Index source to graph JSON",
            "  load [PATH]                                 Load a graph JSON file",
            "  stats                                       Show graph statistics",
            "  find <name> [--limit N]                     Find symbol by fuzzy name",
            "  callers <symbol> [--limit N]                Show callers of a symbol",
            "  related <file> [--depth N] [--limit N]      Show related files",
            "  path <from> <to> [--max-depth N]            Trace shortest path between symbols",
            "  impact <symbol> [--depth N] [--limit N]     Show blast radius for symbol changes",
            "  export graphml [--out PATH]                 Export graph to GraphML",
            "  export neo4j [--out DIR]                    Export graph to Neo4j CSV files",
            "  visual [--out PATH] [--limit N]             Generate D3 visualization HTML",
            "  where                                       Show current graph path",
            "  raw on|off                                  Toggle JSON raw output",
            "  clear                                       Clear the screen",
            "  exit | quit                                 Leave interactive mode",
        ]
    )


def render_stats_panel(stats: dict[str, object], ui: UI) -> None:
    title = f"Nodes: {stats.get('nodes', 0)} | Edges: {stats.get('edges', 0)}"
    ui.print(Panel.fit(title, title="Graph Stats", border_style="cyan"))
    _render_unified_stats_table(stats, ui)


def _render_unified_stats_table(stats: dict[str, object], ui: UI) -> None:
    table = Table(title="All Stats", header_style="bold cyan")
    table.add_column("Section", style="bold")
    table.add_column("Metric")
    table.add_column("Value", justify="right")

    _append_dict_rows(table, "Confidence (count)", stats.get("confidence_counts", {}))
    _append_percent_rows(table, "Confidence (percent)", stats.get("confidence_percentages", {}))
    _append_coverage_rows(table, "Extraction Coverage", stats.get("extraction_coverage", {}))
    _append_dict_rows(table, "Node Types", stats.get("node_types", {}))
    _append_dict_rows(table, "Edge Types", stats.get("edge_types", {}))
    _append_dict_rows(table, "Languages", stats.get("languages", {}))
    _append_incremental_rows(table, "Incremental Cache", stats.get("incremental_cache", {}))

    ui.print(table)


def _append_dict_rows(table: Table, section: str, data: object) -> None:
    if not isinstance(data, dict):
        return
    for key, value in sorted(data.items()):
        table.add_row(section, str(key), str(value))


def _append_percent_rows(table: Table, section: str, data: object) -> None:
    if not isinstance(data, dict):
        return
    for key, value in sorted(data.items()):
        table.add_row(section, str(key), f"{value}%")


def _append_coverage_rows(table: Table, section: str, data: object) -> None:
    if not isinstance(data, dict):
        return
    for lang, row in sorted(data.items()):
        if not isinstance(row, dict):
            continue
        table.add_row(section, f"{lang}.files_seen", str(row.get("files_seen", 0)))
        table.add_row(section, f"{lang}.files_indexed", str(row.get("files_indexed", 0)))
        table.add_row(section, f"{lang}.coverage_percent", f"{row.get('coverage_percent', 0.0)}%")
        table.add_row(section, f"{lang}.parser_mode", str(row.get("parser_mode", "unknown")))


def _append_incremental_rows(table: Table, section: str, data: object) -> None:
    if not isinstance(data, dict):
        return
    for key in ["enabled", "cache_hits", "reindexed_files", "deleted_files", "cache_path"]:
        table.add_row(section, key, str(data.get(key, "-")))


def render_index_summary(summary: dict[str, object], ui: UI) -> None:
    table = Table(title="Index Summary", header_style="bold cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="left")
    for key in [
        "source",
        "resolved",
        "output",
        "excluded_dirs",
        "scanned_files",
        "indexed_files",
        "nodes",
        "edges",
        "cache_hits",
        "reindexed_files",
        "deleted_files",
    ]:
        if key in summary:
            label = key.replace("_", " ").title()
            table.add_row(label, str(summary[key]))
    ui.print(table)


def render_table(title: str, rows: list[dict[str, str]], columns: list[tuple[str, str]], ui: UI) -> None:
    if not rows:
        ui.warn("No results.")
        return
    table = Table(title=title, header_style="bold cyan")
    for key, label in columns:
        justify = "right" if key in {"line", "distance", "step"} else "left"
        table.add_column(label, justify=justify)
    for row in rows:
        table.add_row(*[_truncate(str(row.get(key, "")), 90) for key, _ in columns])
    ui.print(table)


def _truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 3] + "..."
