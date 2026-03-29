from __future__ import annotations

import json
from pathlib import Path

from code_atlas.exporters import build_visual_html
from code_atlas.graph import GraphStore
from code_atlas.indexer import build_graph
from code_atlas.mcp import handlers as mcp_handlers
from code_atlas.query import find_symbol, impact_of, shortest_path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "docs" / "assets" / "demo-run"
    out_dir.mkdir(parents=True, exist_ok=True)

    result = build_graph(root)
    graph_path = root / "tmp" / "code-atlas.graph.json"
    result.graph.write_json(graph_path)
    graph = GraphStore.from_json(graph_path)

    _write_json(out_dir / "cli-stats.json", graph.stats())
    _write_json(out_dir / "cli-find.json", find_symbol(graph, "find_symbol", limit=10))
    _write_json(
        out_dir / "cli-path.json",
        shortest_path(
            graph,
            "python://code_atlas.cli.commands:cmd_find",
            "python://code_atlas.query.basic:find_symbol",
            max_depth=12,
        ),
    )
    _write_json(
        out_dir / "cli-impact.json",
        impact_of(graph, "python://code_atlas.query.basic:find_symbol", depth=3, limit=30),
    )

    _write_json(
        out_dir / "mcp-find-symbol.json",
        mcp_handlers.find(str(graph_path), "find_symbol", 10),
    )
    _write_json(
        out_dir / "mcp-impact-symbol.json",
        mcp_handlers.impact(str(graph_path), "python://code_atlas.query.basic:find_symbol", 3, 30),
    )

    build_visual_html(graph, "find_symbol", out_dir / "visual-workflow.html", open_browser=False)

    transcript = [
        "Demo run artifacts generated:",
        f"- Graph: {graph_path}",
        f"- CLI stats/find/path/impact JSON: {out_dir}",
        f"- MCP find/impact JSON: {out_dir}",
        f"- Visual HTML: {out_dir / 'visual-workflow.html'}",
        "",
        "Capture screenshots/GIF manually from these runs for portfolio assets:",
        "- docs/assets/cli-workflow.png",
        "- docs/assets/visual-workflow.png",
        "- docs/assets/mcp-workflow.png",
        "- docs/assets/code-atlas-demo.gif",
    ]
    (out_dir / "transcript.txt").write_text("\n".join(transcript), encoding="utf-8")
    print("\n".join(transcript))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
