from __future__ import annotations

from .cli_ui import UI


def render_stats_panel(stats: dict[str, object], ui: UI) -> None:
    ui.header("\nGraph Stats")
    print("-" * 54)
    print(f"Nodes: {stats.get('nodes', 0):<10}Edges: {stats.get('edges', 0)}")
    _render_counts("Node Types", stats.get("node_types", {}))
    _render_counts("Edge Types", stats.get("edge_types", {}))
    _render_counts("Languages", stats.get("languages", {}))


def _render_counts(title: str, data: object) -> None:
    print(f"\n{title}")
    print("-" * 54)
    if not isinstance(data, dict):
        return
    for key, value in sorted(data.items()):
        print(f"{key:<20}{value}")


def render_table(title: str, rows: list[dict[str, str]], columns: list[tuple[str, str]], ui: UI) -> None:
    ui.header(f"\n{title}")
    if not rows:
        ui.warn("No results.")
        return

    widths: dict[str, int] = {}
    for key, label in columns:
        max_cell = max(len(str(row.get(key, ""))) for row in rows)
        widths[key] = max(len(label), min(max_cell, 60))

    print(" | ".join(label.ljust(widths[key]) for key, label in columns))
    print("-+-".join("-" * widths[key] for key, _ in columns))

    for row in rows:
        vals: list[str] = []
        for key, _label in columns:
            text = str(row.get(key, ""))
            if len(text) > widths[key]:
                text = text[: widths[key] - 3] + "..."
            vals.append(text.ljust(widths[key]))
        print(" | ".join(vals))
