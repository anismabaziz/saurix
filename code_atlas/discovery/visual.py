from __future__ import annotations

"""
Hybrid 2D/3D Visualization Module

This module handles the generation of an interactive knowledge graph that supports
both 2D (Canvas) and 3D (WebGL) rendering modes. Users can toggle between modes
in real-time to balance performance and immersion.
"""

import json
from pathlib import Path
from typing import Any

from ..core.graph import GraphStore
from ..infra.config import config
from ..infra.logging import get_logger

logger = get_logger(__name__)

# Hybrid HTML template with 2D/3D switching logic
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Code Atlas Visualization</title>
    <!-- Core graph libraries -->
    <script src="https://unpkg.com/force-graph"></script>
    <script src="https://unpkg.com/3d-force-graph"></script>
    <style>
        body { margin: 0; background: #000; overflow: hidden; font-family: sans-serif; }
        #graph-container { width: 100vw; height: 100vh; }
        
        /* Floating control panel */
        .control-panel {
            position: absolute;
            top: 20px;
            left: 20px;
            background: rgba(13, 17, 23, 0.9);
            border: 1px solid #30363d;
            padding: 15px;
            border-radius: 8px;
            color: #c9d1d9;
            z-index: 10;
            backdrop-filter: blur(8px);
            box-shadow: 0 8px 32px rgba(0,0,0,0.5);
        }
        .control-panel h2 { margin: 0 0 15px 0; font-size: 16px; color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 10px; }
        
        /* Mode Switcher */
        .mode-switch {
            display: flex;
            background: #21262d;
            border-radius: 6px;
            padding: 2px;
            margin-bottom: 15px;
            pointer-events: auto;
        }
        .mode-btn {
            flex: 1;
            padding: 6px 12px;
            text-align: center;
            font-size: 12px;
            cursor: pointer;
            border-radius: 4px;
            transition: all 0.2s;
            color: #8b949e;
        }
        .mode-btn.active {
            background: #58a6ff;
            color: #fff;
            box-shadow: 0 2px 8px rgba(88, 166, 255, 0.4);
        }
        
        .legend { font-size: 12px; line-height: 1.6; }
        .legend-item { display: flex; align-items: center; margin-bottom: 4px; }
        .dot { width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }
        
        /* Tooltip styling override */
        .graph-tooltip {
            background: rgba(22, 27, 34, 0.95) !important;
            border: 1px solid #30363d !important;
            color: #c9d1d9 !important;
            padding: 10px !important;
            border-radius: 6px !important;
        }
    </style>
</head>
<body>
    <div class="control-panel">
        <h2>Code Atlas</h2>
        <div class="mode-switch">
            <div id="btn-2d" class="mode-btn active" onclick="setMode('2D')">2D View</div>
            <div id="btn-3d" class="mode-btn" onclick="setMode('3D')">3D View</div>
        </div>
        <div class="legend">
            <div class="legend-item"><div class="dot" style="background:#58a6ff"></div> Module</div>
            <div class="legend-item"><div class="dot" style="background:#d29922"></div> Class</div>
            <div class="legend-item"><div class="dot" style="background:#238636"></div> Function</div>
            <div class="legend-item"><div class="dot" style="background:#a371f7"></div> Method</div>
            <div class="legend-item"><div class="dot" style="background:#8b949e"></div> File/Other</div>
            <div style="margin-top:10px; color:#8b949e; font-size: 11px;">
                <b>Controls:</b><br/>
                - Left: Rotate (3D) / Pan (2D)<br/>
                - Right: Pan (3D)<br/>
                - Scroll: Zoom<br/>
                - Click Node: Focus
            </div>
        </div>
    </div>
    <div id="graph-container"></div>

    <script>
        const data = __GRAPH_DATA__;
        let currentMode = '2D';
        let graphInstance = null;

        const getColor = node => {
            if (node.type === 'module') return '#58a6ff';
            if (node.type === 'class') return '#d29922';
            if (node.type === 'function') return '#238636';
            if (node.type === 'method') return '#a371f7';
            return '#8b949e';
        };

        const getTooltip = node => `
            <div style="text-align: left;">
                <strong style="color: #58a6ff; font-size: 14px;">${node.name}</strong><br/>
                <span style="color: #8b949e; font-size: 12px;">Type:</span> ${node.type}<br/>
                <span style="color: #8b949e; font-size: 12px;">File:</span> ${node.file || 'N/A'}
            </div>
        `;

        function init2D() {
            if (graphInstance) graphInstance._destructor && graphInstance._destructor();
            document.getElementById('graph-container').innerHTML = '';
            
            graphInstance = ForceGraph()
                (document.getElementById('graph-container'))
                .graphData(data)
                .nodeLabel(getTooltip)
                .nodeColor(getColor)
                .nodeRelSize(6)
                .linkWidth(1.5)
                .linkColor(() => '#30363d')
                .linkDirectionalParticles(2)
                .linkDirectionalParticleSpeed(0.005)
                .onNodeClick(node => {
                    graphInstance.centerAt(node.x, node.y, 1000);
                    graphInstance.zoom(4, 1000);
                });
        }

        function init3D() {
            if (graphInstance) graphInstance._destructor && graphInstance._destructor();
            document.getElementById('graph-container').innerHTML = '';

            graphInstance = ForceGraph3D()
                (document.getElementById('graph-container'))
                .graphData(data)
                .nodeLabel(getTooltip)
                .nodeColor(getColor)
                .nodeRelSize(6)
                .linkWidth(1.5)
                .linkColor(() => '#30363d')
                .linkOpacity(0.4)
                .linkDirectionalParticles(2)
                .linkDirectionalParticleSpeed(0.005)
                .onNodeClick(node => {
                    const distance = 250;
                    const distRatio = 1 + distance/Math.hypot(node.x, node.y, node.z);
                    graphInstance.cameraPosition(
                        { x: node.x * distRatio, y: node.y * distRatio, z: node.z * distRatio },
                        node,
                        2500
                    );
                });
        }

        function setMode(mode) {
            if (mode === currentMode) return;
            currentMode = mode;
            
            // UI Update
            document.getElementById('btn-2d').classList.toggle('active', mode === '2D');
            document.getElementById('btn-3d').classList.toggle('active', mode === '3D');
            
            if (mode === '2D') init2D();
            else init3D();
        }

        // Default to 2D for initial load performance
        init2D();
    </script>
</body>
</html>
"""


def generate_visualization(graph: GraphStore, out_path: Path, limit: int = 5000) -> Path:
    """
    Constructs a hybrid 2D/3D HTML dashboard for the current graph.
    
    Args:
        graph: The active GraphStore containing nodes and edges.
        out_path: Destination path for the .html file.
        limit: Maximum number of nodes to include.
        
    Returns:
        The Path to the generated file.
    """
    nodes = []
    node_ids = set()
    
    # Selection priority: modules > classes > functions > others
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
    html_content = HTML_TEMPLATE.replace("__GRAPH_DATA__", graph_data)
    
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_content, encoding="utf-8")
    
    logger.info(f"Generated Hybrid visualization at {out_path} ({len(nodes)} nodes, {len(links)} links)")
    return out_path
