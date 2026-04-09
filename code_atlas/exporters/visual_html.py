from __future__ import annotations

"""Interactive HTML graph visualization exporter."""

import html
import json
import webbrowser
from pathlib import Path

from ..graph import GraphStore
from ..query import neighborhood_subgraph


def build_visual_html(
    graph: GraphStore,
    symbol: str,
    out_html: Path,
    *,
    depth: int = 2,
    limit: int = 120,
    open_browser: bool = True,
) -> Path:
    """Generate an interactive subgraph HTML file and optionally open browser."""
    nodes, edges = neighborhood_subgraph(graph, symbol, depth=depth, limit=limit)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "mode": "neighborhood",
            "nodes_total": len(nodes),
            "edges_total": len(edges),
            "nodes_shown": len(nodes),
            "edges_shown": len(edges),
            "truncated": False,
        },
    }
    out_html.write_text(
        _render_html(payload_json=json.dumps(payload), label=f"center: {symbol}"),
        encoding="utf-8",
    )
    if open_browser:
        webbrowser.open(out_html.resolve().as_uri())
    return out_html


def build_visual_html_all(
    graph: GraphStore,
    out_html: Path,
    *,
    node_limit: int = 800,
    open_browser: bool = True,
) -> Path:
    """Generate and open an interactive HTML view for the whole graph."""
    out_html.parent.mkdir(parents=True, exist_ok=True)
    payload = _build_full_graph_payload(graph, node_limit=node_limit)
    out_html.write_text(
        _render_html(payload_json=json.dumps(payload), label="full knowledge graph"),
        encoding="utf-8",
    )
    if open_browser:
        webbrowser.open(out_html.resolve().as_uri())
    return out_html


def _build_full_graph_payload(graph: GraphStore, *, node_limit: int) -> dict[str, object]:
    total_nodes = len(graph.nodes)
    total_edges = len(graph.edges)

    limit = max(1, node_limit)
    degrees: dict[str, int] = {node_id: 0 for node_id in graph.nodes}
    for edge in graph.edges:
        if edge.source in degrees:
            degrees[edge.source] += 1
        if edge.target in degrees:
            degrees[edge.target] += 1

    sorted_ids = sorted(graph.nodes.keys(), key=lambda node_id: (-degrees.get(node_id, 0), node_id))
    selected_ids = set(sorted_ids[:limit])

    nodes: list[dict[str, str]] = []
    for node_id in sorted(selected_ids):
        node = graph.nodes[node_id]
        nodes.append(
            {
                "id": node.id,
                "label": node.name,
                "type": node.type,
                "file": node.file or "",
                "language": node.language,
            }
        )

    edge_limit = min(max(limit * 4, 1200), 6000)
    kept_edges: list[dict[str, str | None]] = []
    for edge in graph.edges:
        if edge.source in selected_ids and edge.target in selected_ids:
            kept_edges.append(
                {
                    "source": edge.source,
                    "target": edge.target,
                    "type": edge.type,
                    "confidence": edge.confidence,
                }
            )
            if len(kept_edges) >= edge_limit:
                break

    return {
        "nodes": nodes,
        "edges": kept_edges,
        "meta": {
            "mode": "full",
            "nodes_total": total_nodes,
            "edges_total": total_edges,
            "nodes_shown": len(nodes),
            "edges_shown": len(kept_edges),
            "truncated": total_nodes > len(nodes) or total_edges > len(kept_edges),
            "node_limit": limit,
            "edge_limit": edge_limit,
        },
    }


def _render_html(*, payload_json: str, label: str) -> str:
    safe_label = html.escape(label)
    payload_safe = payload_json.replace("</script>", "<\\/script>")
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Code Atlas Graph View</title>
  <style>
    :root {{
      --bg: #050914;
      --bg-grad-a: #13203f;
      --bg-grad-b: #0f2f38;
      --panel: rgba(12, 20, 37, 0.86);
      --line: rgba(126, 147, 188, 0.35);
      --text: #e8f0ff;
      --muted: #9bb0d9;
      --accent: #6ee7d6;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ width: 100%; height: 100%; }}
    body {{
      margin: 0;
      color: var(--text);
      font-family: ui-monospace, Menlo, Consolas, monospace;
      background:
        radial-gradient(1200px 800px at 12% -10%, var(--bg-grad-a), transparent 60%),
        radial-gradient(1000px 700px at 95% 0%, var(--bg-grad-b), transparent 60%),
        var(--bg);
      overflow: hidden;
    }}
    .top {{
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      z-index: 20;
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      padding: 10px 12px;
      background: var(--panel);
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(8px);
    }}
    .chip {{
      font-size: 11px;
      padding: 3px 8px;
      border-radius: 999px;
      color: var(--accent);
      border: 1px solid color-mix(in srgb, var(--accent) 50%, transparent);
      background: color-mix(in srgb, var(--accent) 14%, transparent);
    }}
    .ctl {{
      background: rgba(17, 30, 55, 0.9);
      color: var(--text);
      border: 1px solid var(--line);
      border-radius: 8px;
      font-size: 12px;
      padding: 6px 8px;
    }}
    .ctl::placeholder {{ color: var(--muted); }}
    .btn {{ cursor: pointer; }}
    .btn:hover {{ border-color: color-mix(in srgb, var(--accent) 70%, transparent); }}
    .filters, .pathctl {{
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
      font-size: 12px;
      color: var(--muted);
    }}
    #view {{
      position: fixed;
      top: 68px;
      left: 0;
      right: 0;
      bottom: 0;
    }}
    .panel {{
      position: fixed;
      right: 14px;
      top: 86px;
      width: min(360px, calc(100vw - 28px));
      z-index: 25;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
      font-size: 12px;
      line-height: 1.45;
      backdrop-filter: blur(8px);
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
    }}
    .legend {{
      margin-top: 8px;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 5px;
    }}
    .dot {{
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      margin-right: 6px;
      vertical-align: middle;
    }}
    .error {{
      color: #fecaca;
      border: 1px solid rgba(239, 68, 68, 0.5);
      border-radius: 8px;
      padding: 8px;
      margin-top: 8px;
      background: rgba(127, 29, 29, 0.35);
    }}
    @media (max-width: 960px) {{
      .panel {{ left: 12px; right: 12px; top: auto; bottom: 12px; width: auto; }}
    }}
  </style>
</head>
<body>
  <div class=\"top\">
    <span class=\"chip\">Code Atlas Visual</span>
    <span class=\"chip\">{safe_label}</span>
    <input id=\"search\" class=\"ctl\" placeholder=\"Search node name/id\" style=\"min-width:240px\" />
    <div class=\"filters\">
      <label><input type=\"checkbox\" class=\"etype\" value=\"CALLS\" checked /> CALLS</label>
      <label><input type=\"checkbox\" class=\"etype\" value=\"IMPORTS\" checked /> IMPORTS</label>
      <label><input type=\"checkbox\" class=\"etype\" value=\"CONTAINS\" checked /> CONTAINS</label>
      <label><input type=\"checkbox\" class=\"etype\" value=\"INHERITS\" checked /> INHERITS</label>
    </div>
    <div class=\"pathctl\">
      <input id=\"pathFrom\" class=\"ctl\" placeholder=\"Path from\" style=\"min-width:140px\" />
      <input id=\"pathTo\" class=\"ctl\" placeholder=\"Path to\" style=\"min-width:140px\" />
      <label><input type=\"checkbox\" id=\"pathUndirected\" checked /> Undirected</label>
      <label><input type=\"checkbox\" id=\"pathIgnoreFilters\" checked /> Ignore filters</label>
      <button id=\"pathBtn\" class=\"ctl btn\">Highlight Path</button>
      <button id=\"pathClear\" class=\"ctl btn\">Clear Path</button>
    </div>
    <button id=\"fit\" class=\"ctl btn\">Fit</button>
    <button id=\"pause\" class=\"ctl btn\">Pause</button>
    <button id=\"reset\" class=\"ctl btn\">Reset</button>
  </div>

  <div id=\"view\"></div>

  <div class=\"panel\" id=\"panel\">
    <strong>Hover node to inspect details.</strong>
    <div id=\"counts\" style=\"margin-top:8px;color:var(--muted)\"></div>
    <div class=\"legend\" id=\"legend\"></div>
  </div>

  <script src=\"https://unpkg.com/force-graph@1.49.5/dist/force-graph.min.js\"></script>
  <script src=\"https://unpkg.com/three@0.160.0/build/three.min.js\"></script>
  <script src=\"https://unpkg.com/3d-force-graph@1.77.0/dist/3d-force-graph.min.js\"></script>
  <script>
    const data = {payload_safe};

    const panel = document.getElementById("panel");
    const search = document.getElementById("search");
    const pathFrom = document.getElementById("pathFrom");
    const pathTo = document.getElementById("pathTo");
    const pathUndirected = document.getElementById("pathUndirected");
    const pathIgnoreFilters = document.getElementById("pathIgnoreFilters");
    const fitBtn = document.getElementById("fit");
    const pauseBtn = document.getElementById("pause");
    const resetBtn = document.getElementById("reset");
    const pathBtn = document.getElementById("pathBtn");
    const pathClear = document.getElementById("pathClear");

    const colors = {{
      module: "#60a5fa",
      class: "#fbbf24",
      function: "#34d399",
      method: "#10b981",
      interface: "#f472b6",
      property: "#fb7185",
      symbol: "#c084fc",
      file: "#fb923c",
      repo: "#f43f5e"
    }};

    const baseNodes = (data.nodes || []).map(n => ({{ ...n }}));
    const baseLinks = (data.edges || []).map(e => ({{ ...e }}));
    const nodeIdOf = value => (value && typeof value === "object") ? value.id : value;
    const edgeKey = e => `${{nodeIdOf(e.source)}}->${{nodeIdOf(e.target)}}`;

    let paused = false;
    let highlightedNodes = new Set();
    let highlightedEdges = new Set();

    function selectedEdgeTypes() {{
      return new Set(
        Array.from(document.querySelectorAll(".etype"))
          .filter(c => c.checked)
          .map(c => c.value)
      );
    }}

    function filteredLinks() {{
      const types = selectedEdgeTypes();
      return baseLinks.filter(e => types.has(e.type));
    }}

    function linksForPath() {{
      return pathIgnoreFilters.checked ? baseLinks : filteredLinks();
    }}

    function renderLegend() {{
      const legend = document.getElementById("legend");
      if (!legend) return;
      legend.innerHTML = "";
      Object.entries(colors).forEach(([k, v]) => {{
        const item = document.createElement("div");
        item.innerHTML = `<span class=\"dot\" style=\"background:${{v}}\"></span>${{k}}`;
        legend.appendChild(item);
      }});
    }}

    function updateCounts(nodeCount, edgeCount) {{
      const counts = document.getElementById("counts");
      if (!counts) return;
      const m = data.meta || {{}};
      const totals = (m.nodes_total && m.edges_total)
        ? ` / Total: <strong>${{m.nodes_total}}</strong> nodes, <strong>${{m.edges_total}}</strong> edges`
        : "";
      const trunc = m.truncated ? " <span style=\"color:#fca5a5\">(truncated)</span>" : "";
      counts.innerHTML = `Shown: <strong>${{nodeCount}}</strong> nodes | <strong>${{edgeCount}}</strong> edges${{totals}}${{trunc}}`;
    }}

    function confidenceColor(confidence) {{
      if (confidence === "high") return "#6ee7b7";
      if (confidence === "medium") return "#93c5fd";
      return "#fca5a5";
    }}

    const isFullMode = (data.meta || {{}}).mode === "full";
    const canUse2D = typeof ForceGraph !== "undefined";
    const canUse3D = typeof ForceGraph3D !== "undefined";
    const rendererFactory = (isFullMode && canUse2D)
      ? ForceGraph
      : (canUse3D ? ForceGraph3D : (canUse2D ? ForceGraph : null));

    if (!rendererFactory) {{
      panel.innerHTML = `<strong>Graph unavailable</strong><div class=\"error\">Could not load graph libraries from CDN. Check internet access or firewall settings.</div>`;
      throw new Error("No graph renderer available");
    }}

    const graph = rendererFactory()(document.getElementById("view"))
      .backgroundColor("#050914")
      .width(window.innerWidth)
      .height(Math.max(window.innerHeight - 68, 240))
      .nodeId("id")
      .nodeLabel(n => `${{n.label}}<br/>${{n.type}}<br/>${{n.id}}`)
      .nodeColor(n => highlightedNodes.has(n.id) ? "#f59e0b" : (colors[n.type] || "#94a3b8"))
      .nodeVal(n => highlightedNodes.has(n.id) ? 9 : (n.type === "symbol" ? 4 : 6))
      .linkSource("source")
      .linkTarget("target")
      .linkWidth(l => highlightedEdges.has(edgeKey(l)) ? 3.8 : (l.type === "CALLS" ? 1.8 : 1.2))
      .linkColor(l => highlightedEdges.has(edgeKey(l)) ? "#f59e0b" : confidenceColor(l.confidence))
      .linkDirectionalParticles(l => highlightedEdges.has(edgeKey(l)) ? 4 : 0)
      .linkDirectionalParticleSpeed(0.007)
      .onNodeHover(node => {{
        if (!node) {{
          panel.innerHTML = `<strong>Hover node to inspect details.</strong><div id=\"counts\" style=\"margin-top:8px;color:var(--muted)\"></div><div class=\"legend\" id=\"legend\"></div>`;
          renderLegend();
          updateCounts(baseNodes.length, filteredLinks().length);
          return;
        }}
        panel.innerHTML = `
          <strong>${{node.label}}</strong><br/>
          Type: ${{node.type}}<br/>
          Language: ${{node.language || "-"}}<br/>
          ID: ${{node.id}}<br/>
          File: ${{node.file || "-"}}
          <div id=\"counts\" style=\"margin-top:8px;color:var(--muted)\"></div>
          <div class=\"legend\" id=\"legend\"></div>
        `;
        renderLegend();
        updateCounts(baseNodes.length, filteredLinks().length);
      }});

    if (isFullMode && typeof graph.numDimensions === "function") {{
      graph.numDimensions(2);
    }}

    function applyGraphData() {{
      graph.graphData({{ nodes: baseNodes, links: filteredLinks() }});
      updateCounts(baseNodes.length, filteredLinks().length);
      if (!baseNodes.length) {{
        panel.innerHTML = `<strong>No nodes to render.</strong><div class=\"error\">This graph export is empty.</div>`;
      }}
      graph.refresh();
    }}

    function resolveNode(query) {{
      if (!query || !query.trim()) return null;
      const q = query.trim().toLowerCase();
      return (
        baseNodes.find(n => n.id.toLowerCase() === q)
        || baseNodes.find(n => n.label.toLowerCase() === q)
        || baseNodes.find(n => n.id.toLowerCase().includes(q) || n.label.toLowerCase().includes(q))
        || null
      );
    }}

    function clearPath() {{
      highlightedNodes = new Set();
      highlightedEdges = new Set();
      graph.refresh();
    }}

    function highlightPath() {{
      const sourceNode = resolveNode(pathFrom.value);
      const targetNode = resolveNode(pathTo.value);
      clearPath();
      if (!sourceNode || !targetNode) {{
        panel.innerHTML = `<strong>Path</strong><br/>Could not resolve one or both nodes.`;
        return;
      }}

      const adjacency = new Map();
      for (const e of linksForPath()) {{
        const sourceId = nodeIdOf(e.source);
        const targetId = nodeIdOf(e.target);
        const forward = adjacency.get(sourceId) || [];
        forward.push({{ source: sourceId, target: targetId, type: e.type, confidence: e.confidence }});
        adjacency.set(sourceId, forward);
        if (pathUndirected.checked) {{
          const reverse = adjacency.get(targetId) || [];
          reverse.push({{ source: targetId, target: sourceId, type: e.type, confidence: e.confidence }});
          adjacency.set(targetId, reverse);
        }}
      }}

      const queue = [sourceNode.id];
      const prev = new Map([[sourceNode.id, null]]);
      let hit = null;
      while (queue.length) {{
        const cur = queue.shift();
        if (cur === targetNode.id) {{ hit = cur; break; }}
        const next = adjacency.get(cur) || [];
        for (const e of next) {{
          if (prev.has(e.target)) continue;
          prev.set(e.target, e);
          queue.push(e.target);
        }}
      }}
      if (!hit) {{
        panel.innerHTML = `<strong>Path</strong><br/>No path found. Try enabling more edge types or checking Ignore filters.`;
        return;
      }}

      let cursor = hit;
      let hops = 0;
      while (cursor && prev.has(cursor)) {{
        highlightedNodes.add(cursor);
        const e = prev.get(cursor);
        if (!e) break;
        highlightedEdges.add(`${{e.source}}->${{e.target}}`);
        cursor = e.source;
        hops += 1;
      }}
      highlightedNodes.add(sourceNode.id);
      graph.refresh();
      panel.innerHTML = `
        <strong>Path highlighted</strong><br/>
        From: ${{sourceNode.label}}<br/>
        To: ${{targetNode.label}}<br/>
        Hops: ${{hops}}<br/>
        Mode: ${{pathUndirected.checked ? "undirected" : "directed"}}
      `;
    }}

    function focusNode(node) {{
      if (!node) return;
      if (typeof graph.cameraPosition === "function") {{
        const distance = 180;
        const distRatio = 1 + distance / Math.hypot(node.x || 1, node.y || 1, node.z || 1);
        graph.cameraPosition(
          {{ x: (node.x || 0) * distRatio, y: (node.y || 0) * distRatio, z: (node.z || 0) * distRatio }},
          node,
          900
        );
      }} else {{
        graph.centerAt(node.x || 0, node.y || 0, 700);
        graph.zoom(3, 700);
      }}
    }}

    document.querySelectorAll(".etype").forEach(el => el.addEventListener("change", applyGraphData));
    search.addEventListener("keydown", ev => {{
      if (ev.key !== "Enter") return;
      const node = resolveNode(search.value);
      if (!node) return;
      highlightedNodes = new Set([node.id]);
      highlightedEdges = new Set();
      graph.refresh();
      focusNode(node);
    }});
    fitBtn.addEventListener("click", () => {{
      if (typeof graph.zoomToFit === "function") graph.zoomToFit(500, 40);
    }});
    pauseBtn.addEventListener("click", () => {{
      paused = !paused;
      pauseBtn.textContent = paused ? "Resume" : "Pause";
      if (typeof graph.pauseAnimation === "function" && typeof graph.resumeAnimation === "function") {{
        if (paused) graph.pauseAnimation();
        else graph.resumeAnimation();
      }}
    }});
    resetBtn.addEventListener("click", () => {{
      search.value = "";
      pathFrom.value = "";
      pathTo.value = "";
      document.querySelectorAll(".etype").forEach(c => {{ c.checked = true; }});
      clearPath();
      applyGraphData();
      if (typeof graph.zoomToFit === "function") graph.zoomToFit(600, 50);
    }});
    pathBtn.addEventListener("click", highlightPath);
    pathClear.addEventListener("click", () => {{
      pathFrom.value = "";
      pathTo.value = "";
      clearPath();
      panel.innerHTML = `<strong>Path cleared.</strong>`;
    }});

    renderLegend();
    applyGraphData();
    if ((data.meta || {{}}).truncated) {{
      const note = document.createElement("div");
      note.className = "error";
      note.style.borderColor = "rgba(245, 158, 11, 0.45)";
      note.style.background = "rgba(120, 53, 15, 0.35)";
      note.style.color = "#fde68a";
      note.textContent = "Large graph mode: showing a capped subset for browser performance.";
      panel.appendChild(note);
    }}
    setTimeout(() => {{
      if (typeof graph.zoomToFit === "function") graph.zoomToFit(800, 60);
    }}, 250);
    window.addEventListener("resize", () => {{
      graph.width(window.innerWidth);
      graph.height(Math.max(window.innerHeight - 68, 240));
    }});
  </script>
</body>
</html>
"""
