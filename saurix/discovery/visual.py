"""
2D Visualization Module with Search & Filtering

This module generates a 2D interactive knowledge graph dashboard with
search highlighting and tooltips.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..core.graph import GraphStore

logger = logging.getLogger(__name__)


def _load_template() -> str:
    """
    Load the dashboard HTML template from the asset file.
    """
    # Primary: package asset at saurix/assets/dashboard.html
    asset_path = Path(__file__).resolve().parent.parent / "assets" / "dashboard.html"
    if asset_path.exists():
        return asset_path.read_text(encoding="utf-8")
    # Fallback: try importlib.resources for installed packages
    try:
        from importlib.resources import files

        template = files("saurix.assets").joinpath("dashboard.html")  # type: ignore[arg-type]
        return template.read_text(encoding="utf-8")
    except Exception:
        pass
    raise FileNotFoundError(f"Dashboard template not found at {asset_path}")


def generate_visualization(
    graph: GraphStore, out_path: Path, limit: int = 5000
) -> Path:
    """
    Constructs a 2D HTML dashboard with search and filtering.
    """
    symbols = []
    symbol_ids = set()

    all_symbols = sorted(graph.symbols.values(), key=lambda s: (s.type, s.id))[:limit]
    for symbol in all_symbols:
        symbols.append(
            {
                "id": symbol.id,
                "name": symbol.name,
                "type": symbol.type,
                "file": symbol.file,
            }
        )
        symbol_ids.add(symbol.id)

    links = []
    for edge in graph.edges:
        if edge.source in symbol_ids and edge.target in symbol_ids:
            links.append(
                {
                    "source": edge.source,
                    "target": edge.target,
                    "type": edge.type,
                }
            )

    # force-graph reads `nodes` and `links` from the object it is handed, so those
    # two keys are the library's contract rather than this project's vocabulary.
    graph_data = json.dumps({"nodes": symbols, "links": links})
    template = _load_template()
    html_content = template.replace("__GRAPH_DATA__", graph_data)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_content, encoding="utf-8")

    logger.info(f"Generated visualization at {out_path} ({len(symbols)} symbols)")
    return out_path
