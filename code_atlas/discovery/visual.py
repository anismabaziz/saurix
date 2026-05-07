from __future__ import annotations

"""
3D Visualization Module

This module handles the generation of an interactive 3D knowledge graph.
It uses '3d-force-graph' (built on Three.js) to render a WebGL-powered 3D space
where users can explore repository symbols, dependencies, and call hierarchies.
"""

import json
from pathlib import Path
from typing import Any

from ..core.graph import GraphStore
from ..infra.config import config
from ..infra.logging import get_logger

logger = get_logger(__name__)

# Immersive 3D visualization using 3d-force-graph (Three.js)
# We use a standalone HTML template to ensure the result is portable and easy to share.
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Code Atlas 3D</title>
    <!-- External library for high-performance 3D force-directed graphs -->
    <script src="https://unpkg.com/3d-force-graph"></script>
    <style>
        body { margin: 0; background: #000; overflow: hidden; font-family: sans-serif; }
        #3d-graph { width: 100vw; height: 100vh; }
        
        /* Floating control panel with legend */
        .control-panel {
            position: absolute;
            top: 20px;
            left: 20px;
            background: rgba(13, 17, 23, 0.85);
            border: 1px solid #30363d;
            padding: 15px;
            border-radius: 8px;
            color: #c9d1d9;
            pointer-events: none;
            z-index: 10;
            backdrop-filter: blur(4px);
        }
        .control-panel h2 { margin: 0 0 10px 0; font-size: 16px; color: #58a6ff; }
        .legend { font-size: 12px; line-height: 1.6; }
        .legend-item { display: flex; align-items: center; margin-bottom: 4px; }
        .dot { width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }
    </style>
</head>
<body>
    <div class="control-panel">
        <h2>Code Atlas 3D</h2>
        <div class="legend">
            <div class="legend-item"><div class="dot" style="background:#58a6ff"></div> Module</div>
            <div class="legend-item"><div class="dot" style="background:#d29922"></div> Class</div>
            <div class="legend-item"><div class="dot" style="background:#238636"></div> Function</div>
            <div class="legend-item"><div class="dot" style="background:#a371f7"></div> Method</div>
            <div class="legend-item"><div class="dot" style="background:#8b949e"></div> File/Other</div>
            <div style="margin-top:10px; color:#8b949e">Left-click: Rotate<br>Right-click: Pan<br>Scroll: Zoom</div>
        </div>
    </div>
    <div id="3d-graph"></div>

    <script>
        // Data injected by Python generator
        const data = __GRAPH_DATA__;
        
        // Initialize the 3D Graph
        const Graph = ForceGraph3D()
            (document.getElementById('3d-graph'))
            .graphData(data)
            .nodeLabel(node => `
                <div style="background: rgba(22, 27, 34, 0.95); border: 1px solid #30363d; padding: 10px; border-radius: 6px; color: #c9d1d9; box-shadow: 0 4px 12px rgba(0,0,0,0.5);">
                    <strong style="color: #58a6ff; font-size: 14px;">${node.name}</strong><br/>
                    <span style="color: #8b949e; font-size: 12px;">Type:</span> ${node.type}<br/>
                    <span style="color: #8b949e; font-size: 12px;">File:</span> ${node.file || 'N/A'}
                </div>
            `)
            .nodeColor(node => {
                // Color scheme matched with the legend
                if (node.type === 'module') return '#58a6ff';
                if (node.type === 'class') return '#d29922';
                if (node.type === 'function') return '#238636';
                if (node.type === 'method') return '#a371f7';
                return '#8b949e';
            })
            .nodeRelSize(6)
            .linkWidth(1.5)
            .linkColor(() => '#30363d')
            .linkOpacity(0.4)
            .linkDirectionalParticles(2)
            .linkDirectionalParticleSpeed(d => 0.005)
            .onNodeClick(node => {
                // Smooth camera transition to focus on the clicked node
                const distance = 250;
                const distRatio = 1 + distance/Math.hypot(node.x, node.y, node.z);

                Graph.cameraPosition(
                    { x: node.x * distRatio, y: node.y * distRatio, z: node.z * distRatio }, 
                    node, // lookAt location
                    2500  // transition duration in ms
                );
            });

        // Apply visual polish (Bloom/Glow)
        Graph.postProcessingComposer().addPass(new THREE.UnrealBloomPass());
    </script>
</body>
</html>
"""


def generate_visualization(graph: GraphStore, out_path: Path, limit: int = 5000) -> Path:
    """
    Constructs a standalone HTML dashboard for the current graph.
    
    Args:
        graph: The active GraphStore containing nodes and edges.
        out_path: Destination path for the .html file.
        limit: Maximum number of nodes to include (defaults to 5000 for 3D).
        
    Returns:
        The Path to the generated file.
    """
    nodes = []
    node_ids = set()
    
    # Sort nodes to ensure consistent rendering and selection when reaching the limit
    all_nodes = sorted(graph.nodes.values(), key=lambda n: (n.type, n.id))[:limit]
    for node in all_nodes:
        nodes.append({
            "id": node.id,
            "name": node.name,
            "type": node.type,
            "file": node.file,
        })
        node_ids.add(node.id)

    # Only include edges where both endpoints were accepted in the node limit
    links = []
    for edge in graph.edges:
        if edge.source in node_ids and edge.target in node_ids:
            links.append({
                "source": edge.source,
                "target": edge.target,
                "type": edge.type,
            })

    # Prepare data and inject into the static template
    graph_data = json.dumps({"nodes": nodes, "links": links})
    html_content = HTML_TEMPLATE.replace("__GRAPH_DATA__", graph_data)
    
    # Write the result to disk
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_content, encoding="utf-8")
    
    logger.info(f"Generated 3D visualization at {out_path} ({len(nodes)} nodes, {len(links)} links)")
    return out_path
