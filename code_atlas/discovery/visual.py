from __future__ import annotations

"""Lightweight D3.js based graph visualizer."""

import json
from pathlib import Path
from typing import Any

from ..core.graph import GraphStore
from ..infra.config import config
from ..infra.logging import get_logger

logger = get_logger(__name__)

# Use a static string and .replace() to avoid Python string formatting brace issues
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Code Atlas Visualization</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        :root {
            --bg-color: #0d1117;
            --text-color: #c9d1d9;
            --link-color: #30363d;
            --node-stroke: #ffffff;
        }
        body {
            margin: 0;
            background: var(--bg-color);
            color: var(--text-color);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            overflow: hidden;
        }
        #viz {
            width: 100vw;
            height: 100vh;
        }
        .links line {
            stroke: var(--link-color);
            stroke-opacity: 0.6;
        }
        .nodes circle {
            stroke: var(--node-stroke);
            stroke-width: 1.5px;
            cursor: pointer;
        }
        text {
            font-size: 10px;
            pointer-events: none;
            fill: #8b949e;
        }
        .tooltip {
            position: absolute;
            background: rgba(22, 27, 34, 0.9);
            border: 1px solid #30363d;
            padding: 10px;
            border-radius: 6px;
            font-size: 12px;
            pointer-events: none;
            visibility: hidden;
            z-index: 10;
            box-shadow: 0 4px 12px rgba(0,0,0,0.5);
            max-width: 300px;
            word-wrap: break-word;
        }
    </style>
</head>
<body>
    <div id="tooltip" class="tooltip"></div>
    <svg id="viz"></svg>

    <script>
        const data = __GRAPH_DATA__;
        if (!data.nodes || data.nodes.length === 0) {
            document.body.innerHTML = '<div style="display:flex;justify-content:center;align-items:center;height:100vh;color:#8b949e">No nodes to visualize. Index a repository first.</div>';
            throw new Error("No nodes to visualize");
        }

        const width = window.innerWidth;
        const height = window.innerHeight;

        const svg = d3.select("#viz")
            .attr("width", width)
            .attr("height", height)
            .attr("viewBox", [0, 0, width, height]);

        const container = svg.append("g");

        svg.call(d3.zoom()
            .extent([[0, 0], [width, height]])
            .scaleExtent([0.05, 10])
            .on("zoom", (event) => {
                container.attr("transform", event.transform);
            }));

        const simulation = d3.forceSimulation(data.nodes)
            .force("link", d3.forceLink(data.links).id(d => d.id).distance(80))
            .force("charge", d3.forceManyBody().strength(-300))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("collide", d3.forceCollide().radius(30));

        const link = container.append("g")
            .attr("class", "links")
            .selectAll("line")
            .data(data.links)
            .enter().append("line")
            .attr("stroke-width", 1.5);

        const node = container.append("g")
            .attr("class", "nodes")
            .selectAll("circle")
            .data(data.nodes)
            .enter().append("circle")
            .attr("r", 8)
            .attr("fill", d => {
                if (d.type === 'module') return '#58a6ff';
                if (d.type === 'class') return '#d29922';
                if (d.type === 'function') return '#238636';
                if (d.type === 'method') return '#a371f7';
                return '#8b949e';
            })
            .call(d3.drag()
                .on("start", dragstarted)
                .on("drag", dragged)
                .on("end", dragended));

        const label = container.append("g")
            .selectAll("text")
            .data(data.nodes)
            .enter().append("text")
            .text(d => d.name)
            .attr("dx", 12)
            .attr("dy", 4);

        const tooltip = d3.select("#tooltip");

        node.on("mouseover", (event, d) => {
            tooltip.style("visibility", "visible")
                   .html(`<strong>${d.name}</strong><br/><span style="color:#8b949e">Type:</span> ${d.type}<br/><span style="color:#8b949e">File:</span> ${d.file || 'N/A'}`);
            
            d3.select(event.currentTarget).attr("r", 10).style("stroke", "#58a6ff");
        })
        .on("mousemove", (event) => {
            tooltip.style("top", (event.pageY - 10) + "px")
                   .style("left", (event.pageX + 10) + "px");
        })
        .on("mouseout", (event) => {
            tooltip.style("visibility", "hidden");
            d3.select(event.currentTarget).attr("r", 8).style("stroke", "#ffffff");
        });

        simulation.on("tick", () => {
            link.attr("x1", d => d.source.x)
                .attr("y1", d => d.source.y)
                .attr("x2", d => d.target.x)
                .attr("y2", d => d.target.y);

            node.attr("cx", d => d.x)
                .attr("cy", d => d.y);

            label.attr("x", d => d.x)
                 .attr("y", d => d.y);
        });

        function dragstarted(event, d) {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
        }

        function dragged(event, d) {
            d.fx = event.x;
            d.fy = event.y;
        }

        function dragended(event, d) {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
        }
    </script>
</body>
</html>
"""


def generate_visualization(graph: GraphStore, out_path: Path, limit: int = 2000) -> Path:
    """Generate a standalone HTML visualization of the graph."""
    nodes = []
    node_ids = set()
    
    # Cap results for performance
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
    # Use .replace() instead of .format() to avoid brace escaping issues
    html_content = HTML_TEMPLATE.replace("__GRAPH_DATA__", graph_data)
    
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_content, encoding="utf-8")
    
    logger.info(f"Generated visualization at {out_path} ({len(nodes)} nodes, {len(links)} links)")
    return out_path
