from __future__ import annotations

"""
Hybrid 2D/3D Visualization Module with Search & Filtering

This module handles the generation of an interactive knowledge graph that supports
both 2D and 3D rendering modes, along with real-time searching and filtering.
"""

import json
from pathlib import Path
from typing import Any

from ..core.graph import GraphStore
from ..infra.config import config
from ..infra.logging import get_logger

logger = get_logger(__name__)

# Hybrid HTML template with 2D/3D switching and Search logic
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Code Atlas Visualization</title>
    <script src="https://unpkg.com/force-graph"></script>
    <script src="https://unpkg.com/3d-force-graph"></script>
    <style>
        body { margin: 0; background: #000; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
        #graph-container { width: 100vw; height: 100vh; }
        
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
            width: 260px;
        }
        .control-panel h2 { margin: 0 0 15px 0; font-size: 16px; color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 10px; }
        
        /* Search Box */
        .search-box {
            margin-bottom: 15px;
        }
        .search-input {
            width: 100%;
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 8px 12px;
            color: #c9d1d9;
            font-size: 13px;
            box-sizing: border-box;
            outline: none;
            transition: border-color 0.2s;
        }
        .search-input:focus {
            border-color: #58a6ff;
            box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.3);
        }

        .mode-switch {
            display: flex;
            background: #21262d;
            border-radius: 6px;
            padding: 2px;
            margin-bottom: 15px;
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
        }
        
        .legend { font-size: 12px; line-height: 1.6; }
        .legend-item { display: flex; align-items: center; margin-bottom: 4px; }
        .dot { width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }
        
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
        
        <div class="search-box">
            <input type="text" id="search" class="search-input" placeholder="Search symbols..." oninput="handleSearch(this.value)">
        </div>

        <div class="mode-switch">
            <div id="btn-2d" class="mode-btn active" onclick="setMode('2D')">2D View</div>
            <div id="btn-3d" class="mode-btn" onclick="setMode('3D')">3D View</div>
        </div>

        <div class="legend">
            <div class="legend-item"><div class="dot" style="background:#58a6ff"></div> Module</div>
            <div class="legend-item"><div class="dot" style="background:#d29922"></div> Class</div>
            <div class="legend-item"><div class="dot" style="background:#238636"></div> Function</div>
            <div class="legend-item"><div class="dot" style="background:#a371f7"></div> Method</div>
            <div style="margin-top:10px; color:#8b949e; font-size: 11px;">
                <b>Tip:</b> Searching will highlight matches and dim others. Click a node to focus.
            </div>
        </div>
    </div>
    <div id="graph-container"></div>

    <script>
        const data = __GRAPH_DATA__;
        let currentMode = '2D';
        let graphInstance = null;
        let searchText = '';

        const getColor = node => {
            const isMatch = !searchText || 
                           node.name.toLowerCase().includes(searchText.toLowerCase()) || 
                           node.id.toLowerCase().includes(searchText.toLowerCase());
            
            if (!isMatch) return 'rgba(48, 54, 61, 0.1)'; // Dimmed color

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

        function handleSearch(val) {
            searchText = val;
            if (graphInstance) {
                // Trigger a re-render of colors
                if (currentMode === '2D') {
                    graphInstance.nodeCanvasObject(graphInstance.nodeCanvasObject()); // force update
                } else {
                    graphInstance.nodeColor(graphInstance.nodeColor()); // force update
                }
            }
        }

        function init2D() {
            if (graphInstance) graphInstance._destructor && graphInstance._destructor();
            document.getElementById('graph-container').innerHTML = '';
            
            graphInstance = ForceGraph()
                (document.getElementById('graph-container'))
                .graphData(data)
                .nodeLabel(getTooltip)
                .nodeColor(getColor)
                .nodeRelSize(6)
                .linkWidth(link => {
                    const srcMatch = !searchText || link.source.name.toLowerCase().includes(searchText.toLowerCase());
                    const tgtMatch = !searchText || link.target.name.toLowerCase().includes(searchText.toLowerCase());
                    return (srcMatch || tgtMatch) ? 1.5 : 0.5;
                })
                .linkColor(() => '#30363d')
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
                .linkOpacity(0.2)
                .onNodeClick(node => {
                    const distance = 250;
                    const distRatio = 1 + distance/Math.hypot(node.x, node.y, node.z);
                    graphInstance.cameraPosition(
                        { x: node.x * distRatio, y: node.y * distRatio, z: node.z * distRatio },
                        node,
                        2000
                    );
                });
        }

        function setMode(mode) {
            if (mode === currentMode) return;
            currentMode = mode;
            document.getElementById('btn-2d').classList.toggle('active', mode === '2D');
            document.getElementById('btn-3d').classList.toggle('active', mode === '3D');
            if (mode === '2D') init2D(); else init3D();
        }

        init2D();
    </script>
</body>
</html>
"""


def generate_visualization(graph: GraphStore, out_path: Path, limit: int = 5000) -> Path:
    """Constructs a hybrid 2D/3D HTML dashboard with search and filtering."""
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
    html_content = HTML_TEMPLATE.replace("__GRAPH_DATA__", graph_data)
    
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_content, encoding="utf-8")
    
    logger.info(f"Generated visualization at {out_path} ({len(nodes)} nodes)")
    return out_path
