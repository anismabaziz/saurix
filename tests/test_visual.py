"""Checks that generated dashboards are 2D-only.

Confirms the visualization simplification: the output HTML loads only the 2D
renderer with no 3D library, no mode switch, and no 3D init path, while still
embedding the graph nodes and links.
"""

from __future__ import annotations

from pathlib import Path

from saurix.core.graph import GraphStore
from saurix.core.models import Edge, Node
from saurix.discovery.visual import generate_visualization


def _mini_graph() -> GraphStore:
    """Return a tiny graph with a function calling another."""
    graph = GraphStore()
    graph.add_node(Node(id="python://a", type="function", language="python", name="alpha", file="a.py", line=1))
    graph.add_node(Node(id="python://b", type="function", language="python", name="beta", file="b.py", line=1))
    graph.add_edge(
        Edge(type="CALLS", source="python://a", target="python://b", language="python", confidence="high", file="a.py", line=2)
    )
    return graph


class TestVisualization2DOnly:
    """The generated dashboard is 2D-only and still carries the graph data."""

    def test_writes_dashboard_with_nodes_and_links(self, tmp_path: Path) -> None:
        """The output HTML embeds the graph's nodes and links."""
        out = tmp_path / "viz.html"
        generate_visualization(_mini_graph(), out)

        html = out.read_text(encoding="utf-8")
        assert '"nodes"' in html
        assert '"links"' in html
        assert '"name": "alpha"' in html
        assert '"name": "beta"' in html

    def test_uses_only_the_2d_renderer(self, tmp_path: Path) -> None:
        """The 2D ForceGraph initializer is used, never the 3D variant."""
        out = tmp_path / "viz.html"
        generate_visualization(_mini_graph(), out)

        html = out.read_text(encoding="utf-8")
        assert "ForceGraph()" in html
        assert "ForceGraph3D" not in html

    def test_no_3d_library_or_mode_switch(self, tmp_path: Path) -> None:
        """No three.js import and no 3D mode-switch UI remain in the output."""
        out = tmp_path / "viz.html"
        generate_visualization(_mini_graph(), out)

        html = out.read_text(encoding="utf-8").lower()
        assert "three" not in html
        assert "graphType" not in html