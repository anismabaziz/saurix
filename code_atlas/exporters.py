from __future__ import annotations

import csv
import html
import json
import webbrowser
from pathlib import Path

from .graph import GraphStore
from .query import neighborhood_subgraph


def export_graphml(graph: GraphStore, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    node_keys = [
        ("type", "string"),
        ("language", "string"),
        ("name", "string"),
        ("file", "string"),
        ("line", "int"),
    ]
    edge_keys = [
        ("type", "string"),
        ("language", "string"),
        ("confidence", "string"),
        ("file", "string"),
        ("line", "int"),
    ]

    def esc(value: object) -> str:
        return html.escape(str(value), quote=True)

    with out_path.open("w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<graphml xmlns="http://graphml.graphdrawing.org/xmlns">\n')

        for idx, (name, typ) in enumerate(node_keys):
            f.write(f'  <key id="n{idx}" for="node" attr.name="{name}" attr.type="{typ}"/>\n')
        for idx, (name, typ) in enumerate(edge_keys):
            f.write(f'  <key id="e{idx}" for="edge" attr.name="{name}" attr.type="{typ}"/>\n')

        f.write('  <graph id="G" edgedefault="directed">\n')

        for node in graph.nodes.values():
            f.write(f'    <node id="{esc(node.id)}">\n')
            values = [node.type, node.language, node.name, node.file or "", node.line or ""]
            for idx, value in enumerate(values):
                f.write(f'      <data key="n{idx}">{esc(value)}</data>\n')
            f.write("    </node>\n")

        for i, edge in enumerate(graph.edges):
            f.write(f'    <edge id="edge_{i}" source="{esc(edge.source)}" target="{esc(edge.target)}">\n')
            values = [edge.type, edge.language, edge.confidence, edge.file or "", edge.line or ""]
            for idx, value in enumerate(values):
                f.write(f'      <data key="e{idx}">{esc(value)}</data>\n')
            f.write("    </edge>\n")

        f.write("  </graph>\n")
        f.write("</graphml>\n")

    return out_path


def export_neo4j_csv(graph: GraphStore, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    nodes_csv = out_dir / "nodes.csv"
    edges_csv = out_dir / "edges.csv"

    with nodes_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id:ID", "name", "type", "language", "file", "line:int", ":LABEL"])
        for node in graph.nodes.values():
            writer.writerow([node.id, node.name, node.type, node.language, node.file or "", node.line or "", "Node"])

    with edges_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([":START_ID", ":END_ID", "type", "language", "confidence", "file", "line:int", ":TYPE"])
        for edge in graph.edges:
            writer.writerow([
                edge.source,
                edge.target,
                edge.type,
                edge.language,
                edge.confidence,
                edge.file or "",
                edge.line or "",
                edge.type,
            ])

    return nodes_csv, edges_csv


def build_visual_html(
    graph: GraphStore,
    symbol: str,
    out_html: Path,
    *,
    depth: int = 2,
    limit: int = 120,
    open_browser: bool = True,
) -> Path:
    nodes, edges = neighborhood_subgraph(graph, symbol, depth=depth, limit=limit)
    out_html.parent.mkdir(parents=True, exist_ok=True)

    payload = json.dumps({"nodes": nodes, "edges": edges, "symbol": symbol})

    html_content = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Code Atlas Graph View</title>
  <style>
    :root {{
      --bg: #0b1020;
      --panel: #11182d;
      --text: #dce6ff;
      --muted: #8ea2c9;
      --accent: #4fd1c5;
    }}
    body {{
      margin: 0;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      background: radial-gradient(1200px 800px at 20% -10%, #1a2a52, var(--bg));
      color: var(--text);
    }}
    .top {{
      padding: 14px 18px;
      border-bottom: 1px solid #273555;
      background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0));
    }}
    .top h1 {{ margin: 0; font-size: 15px; }}
    .top p {{ margin: 6px 0 0; color: var(--muted); font-size: 12px; }}
    svg {{ width: 100vw; height: calc(100vh - 74px); display: block; }}
    .node text {{ font-size: 11px; fill: var(--text); pointer-events: none; }}
    .edge {{ stroke: #6f86b5; stroke-opacity: 0.55; }}
    .tip {{
      position: fixed;
      right: 14px;
      top: 84px;
      width: 300px;
      background: rgba(17,24,45,0.92);
      border: 1px solid #304066;
      border-radius: 10px;
      padding: 12px;
      font-size: 12px;
      color: var(--text);
      backdrop-filter: blur(6px);
    }}
    .tip strong {{ color: var(--accent); }}
  </style>
</head>
<body>
  <div class=\"top\">
    <h1>Code Atlas Visual Subgraph</h1>
    <p>Centered on: <strong>{html.escape(symbol)}</strong> | Drag nodes | Mouse wheel to zoom</p>
  </div>
  <svg id=\"view\"></svg>
  <div class=\"tip\" id=\"tip\">Hover node to inspect details.</div>

  <script>
    const data = {payload};
    const width = window.innerWidth;
    const height = window.innerHeight - 74;
    const svg = document.getElementById('view');
    const NS = 'http://www.w3.org/2000/svg';
    const tip = document.getElementById('tip');

    let scale = 1;
    let offsetX = 0;
    let offsetY = 0;

    const g = document.createElementNS(NS, 'g');
    svg.appendChild(g);

    const nodes = data.nodes.map((n, i) => ({{
      ...n,
      x: width / 2 + Math.cos(i * 0.618) * (80 + (i % 12) * 18),
      y: height / 2 + Math.sin(i * 0.618) * (80 + (i % 12) * 18),
      vx: 0,
      vy: 0,
    }}));
    const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
    const links = data.edges
      .map(e => ({{ ...e, source: byId[e.source], target: byId[e.target] }}))
      .filter(e => e.source && e.target);

    function colorOf(type) {{
      const m = {{ module:'#5cc8ff', class:'#f9c74f', function:'#90be6d', method:'#43aa8b', symbol:'#b388eb', file:'#f9844a', repo:'#f94144' }};
      return m[type] || '#9aa5c8';
    }}

    function render() {{
      while (g.firstChild) g.removeChild(g.firstChild);

      for (const e of links) {{
        const line = document.createElementNS(NS, 'line');
        line.setAttribute('class', 'edge');
        line.setAttribute('x1', e.source.x);
        line.setAttribute('y1', e.source.y);
        line.setAttribute('x2', e.target.x);
        line.setAttribute('y2', e.target.y);
        line.setAttribute('stroke-width', e.type === 'CALLS' ? 1.6 : 1.1);
        g.appendChild(line);
      }}

      for (const n of nodes) {{
        const grp = document.createElementNS(NS, 'g');
        grp.setAttribute('class', 'node');
        grp.setAttribute('transform', `translate(${{n.x}},${{n.y}})`);

        const c = document.createElementNS(NS, 'circle');
        c.setAttribute('r', n.type === 'symbol' ? 8 : 11);
        c.setAttribute('fill', colorOf(n.type));
        c.setAttribute('stroke', '#0f172a');
        c.setAttribute('stroke-width', '1.4');
        grp.appendChild(c);

        const t = document.createElementNS(NS, 'text');
        t.setAttribute('x', '14');
        t.setAttribute('y', '4');
        t.textContent = n.label;
        grp.appendChild(t);

        grp.addEventListener('mouseenter', () => {{
          tip.innerHTML = `<strong>${{n.label}}</strong><br/>Type: ${{n.type}}<br/>ID: ${{n.id}}<br/>File: ${{n.file || '-'}}`;
        }});
        enableDrag(grp, n);
        g.appendChild(grp);
      }}

      g.setAttribute('transform', `translate(${{offsetX}},${{offsetY}}) scale(${{scale}})`);
    }}

    function tick() {{
      for (const n of nodes) {{
        n.vx *= 0.92;
        n.vy *= 0.92;
      }}

      for (let i = 0; i < nodes.length; i++) {{
        for (let j = i + 1; j < nodes.length; j++) {{
          const a = nodes[i];
          const b = nodes[j];
          let dx = b.x - a.x;
          let dy = b.y - a.y;
          let d2 = dx*dx + dy*dy + 0.01;
          const force = 1400 / d2;
          a.vx -= force * dx * 0.0008;
          a.vy -= force * dy * 0.0008;
          b.vx += force * dx * 0.0008;
          b.vy += force * dy * 0.0008;
        }}
      }}

      for (const e of links) {{
        const dx = e.target.x - e.source.x;
        const dy = e.target.y - e.source.y;
        const dist = Math.sqrt(dx*dx + dy*dy) || 1;
        const ideal = 110;
        const pull = (dist - ideal) * 0.002;
        const fx = (dx / dist) * pull;
        const fy = (dy / dist) * pull;
        e.source.vx += fx;
        e.source.vy += fy;
        e.target.vx -= fx;
        e.target.vy -= fy;
      }}

      for (const n of nodes) {{
        n.x += n.vx;
        n.y += n.vy;
      }}

      render();
      requestAnimationFrame(tick);
    }}

    function enableDrag(el, node) {{
      let dragging = false;
      el.addEventListener('mousedown', (ev) => {{ dragging = true; ev.preventDefault(); }});
      window.addEventListener('mouseup', () => {{ dragging = false; }});
      window.addEventListener('mousemove', (ev) => {{
        if (!dragging) return;
        node.x = (ev.clientX - offsetX) / scale;
        node.y = (ev.clientY - 74 - offsetY) / scale;
        node.vx = 0;
        node.vy = 0;
      }});
    }}

    svg.addEventListener('wheel', (ev) => {{
      ev.preventDefault();
      const dir = ev.deltaY > 0 ? 0.92 : 1.08;
      scale = Math.max(0.25, Math.min(2.8, scale * dir));
    }});

    let panning = false;
    let startX = 0;
    let startY = 0;
    svg.addEventListener('mousedown', (ev) => {{
      if (ev.target.tagName.toLowerCase() !== 'svg') return;
      panning = true;
      startX = ev.clientX - offsetX;
      startY = ev.clientY - offsetY;
    }});
    window.addEventListener('mouseup', () => {{ panning = false; }});
    window.addEventListener('mousemove', (ev) => {{
      if (!panning) return;
      offsetX = ev.clientX - startX;
      offsetY = ev.clientY - startY;
    }});

    tick();
  </script>
</body>
</html>
"""

    out_html.write_text(html_content, encoding="utf-8")
    if open_browser:
        webbrowser.open(out_html.resolve().as_uri())
    return out_html
