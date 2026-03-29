from __future__ import annotations

from rich.panel import Panel
from rich.table import Table

from .ui import UI


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


def _render_counts_table(title: str, data: object, ui: UI) -> None:
    if not isinstance(data, dict):
        return
    table = Table(title=title, header_style="bold cyan")
    table.add_column("Key", style="bold")
    table.add_column("Value", justify="right")
    for key, value in sorted(data.items()):
        table.add_row(str(key), str(value))
    ui.print(table)


def _render_percentages_table(title: str, data: object, ui: UI) -> None:
    if not isinstance(data, dict):
        return
    table = Table(title=title, header_style="bold cyan")
    table.add_column("Key", style="bold")
    table.add_column("Percent", justify="right")
    for key, value in sorted(data.items()):
        table.add_row(str(key), f"{value}%")
    ui.print(table)


def _render_coverage_table(title: str, data: object, ui: UI) -> None:
    if not isinstance(data, dict):
        return
    table = Table(title=title, header_style="bold cyan")
    table.add_column("Language", style="bold")
    table.add_column("Seen", justify="right")
    table.add_column("Indexed", justify="right")
    table.add_column("Coverage", justify="right")
    table.add_column("Parser", justify="right")
    for lang, row in sorted(data.items()):
        if not isinstance(row, dict):
            continue
        table.add_row(
            str(lang),
            str(row.get("files_seen", 0)),
            str(row.get("files_indexed", 0)),
            f"{row.get('coverage_percent', 0.0)}%",
            str(row.get("parser_mode", "unknown")),
        )
    ui.print(table)


def _render_incremental_table(title: str, data: object, ui: UI) -> None:
    if not isinstance(data, dict):
        return
    table = Table(title=title, header_style="bold cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    for k in ["enabled", "cache_hits", "reindexed_files", "deleted_files", "cache_path"]:
        table.add_row(k, str(data.get(k, "-")))
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
