from __future__ import annotations

from .ui import UI


def render_stats_panel(stats: dict[str, object], ui: UI) -> None:
    ui.header("\nGraph Stats")
    print("=" * 68)
    print(f"Nodes: {stats.get('nodes', 0):<12}Edges: {stats.get('edges', 0)}")
    print("=" * 68)
    _render_counts("Confidence (count)", stats.get("confidence_counts", {}))
    _render_percentages("Confidence (percent)", stats.get("confidence_percentages", {}))
    _render_coverage("Extraction Coverage", stats.get("extraction_coverage", {}))
    _render_counts("Node Types", stats.get("node_types", {}))
    _render_counts("Edge Types", stats.get("edge_types", {}))
    _render_counts("Languages", stats.get("languages", {}))
    _render_incremental("Incremental Cache", stats.get("incremental_cache", {}))


def _render_counts(title: str, data: object) -> None:
    print(f"\n{title}")
    print("-" * 68)
    if isinstance(data, dict):
        for key, value in sorted(data.items()):
            print(f"{key:<20}{value}")


def _render_percentages(title: str, data: object) -> None:
    print(f"\n{title}")
    print("-" * 68)
    if isinstance(data, dict):
        for key, value in sorted(data.items()):
            print(f"{key:<20}{value:>7}%")


def _render_coverage(title: str, data: object) -> None:
    print(f"\n{title}")
    print("-" * 68)
    if not isinstance(data, dict):
        return
    print(f"{'LANG':<14}{'SEEN':>8}{'INDEXED':>10}{'COVERAGE':>12}{'PARSER':>16}")
    print("-" * 68)
    for lang, row in sorted(data.items()):
        if not isinstance(row, dict):
            continue
        seen = row.get("files_seen", 0)
        indexed = row.get("files_indexed", 0)
        pct = row.get("coverage_percent", 0.0)
        parser = row.get("parser_mode", "unknown")
        print(f"{lang:<14}{seen:>8}{indexed:>10}{str(pct) + '%':>12}{parser:>16}")


def render_table(title: str, rows: list[dict[str, str]], columns: list[tuple[str, str]], ui: UI) -> None:
    ui.header(f"\n{title}")
    if not rows:
        ui.warn("No results.")
        return
    widths = {key: max(len(label), min(max(len(str(r.get(key, ""))) for r in rows), 60)) for key, label in columns}
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


def _render_incremental(title: str, data: object) -> None:
    print(f"\n{title}")
    print("-" * 68)
    if not isinstance(data, dict):
        return
    print(f"enabled           {data.get('enabled', False)}")
    print(f"cache_hits        {data.get('cache_hits', 0)}")
    print(f"reindexed_files   {data.get('reindexed_files', 0)}")
    print(f"deleted_files     {data.get('deleted_files', 0)}")
    print(f"cache_path        {data.get('cache_path', '-')}")
