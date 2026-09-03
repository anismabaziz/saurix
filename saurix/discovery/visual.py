from __future__ import annotations

"""
2D Visualization Module with Search & Filtering

This module generates a 2D interactive knowledge graph dashboard with
search highlighting and tooltips.
"""

import json
from pathlib import Path

import logging

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


def generate_visualization(graph: GraphStore, out_path: Path, limit: int = 5000) -> Path:
    """
    Constructs a 2D HTML dashboard with search and filtering.
    """
    nodes = []
    node_ids = set()

    all_nodes = sorted(graph.nodes.values(), key=lambda n: (n.type, n.id))[:limit]
    for node in all_nodes:
        nodes.append({
            "id": node.id,
            "name": node.name,
            "type": node.type,
            "file": node.file,
        })
        node_ids.add(node.id)

    links = []
    for edge in graph.edges:
        if edge.source in node_ids and edge.target in node_ids:
            links.append({
                "source": edge.source,
                "target": edge.target,
                "type": edge.type,
            })

    graph_data = json.dumps({"nodes": nodes, "links": links})
    template = _load_template()
    html_content = template.replace("__GRAPH_DATA__", graph_data)
    
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_content, encoding="utf-8")
    
    logger.info(f"Generated visualization at {out_path} ({len(nodes)} nodes)")
    return out_path
