from __future__ import annotations

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
    nodes, edges = neighborhood_subgraph(graph, symbol, depth=depth, limit=limit)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"nodes": nodes, "edges": edges, "symbol": symbol})

    out_html.write_text(_render_html(symbol, payload), encoding="utf-8")
    if open_browser:
        webbrowser.open(out_html.resolve().as_uri())
    return out_html


def _render_html(symbol: str, payload: str) -> str:
    safe_symbol = html.escape(symbol)
    return f"""<!doctype html>
<html lang=\"en\"><head>
<meta charset=\"utf-8\" /><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
<title>Code Atlas Graph View</title>
<style>
:root {{ --bg:#0b1020; --panel:#10192f; --text:#dce6ff; --muted:#8ea2c9; --accent:#4fd1c5; --line:#304066; }}
body {{ margin:0; font-family:ui-monospace,Menlo,Consolas,monospace; background:radial-gradient(1200px 800px at 20% -10%,#1a2a52,var(--bg)); color:var(--text); }}
.top {{ padding:10px 14px; border-bottom:1px solid #273555; display:flex; gap:10px; align-items:center; flex-wrap:wrap; }}
.chip {{ background:rgba(79,209,197,.12); border:1px solid rgba(79,209,197,.45); color:var(--accent); padding:3px 8px; border-radius:999px; font-size:11px; }}
.ctl {{ background:var(--panel); border:1px solid var(--line); color:var(--text); border-radius:8px; padding:6px 8px; font-size:12px; }}
.btn {{ cursor:pointer; }}
.filters {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; }}
svg {{ width:100vw; height:calc(100vh - 66px); display:block; }}
.node text {{ font-size:11px; fill:var(--text); pointer-events:none; }}
.edge {{ stroke:#6f86b5; stroke-opacity:.55; }}
.panel {{ position:fixed; right:14px; top:76px; width:320px; background:rgba(16,25,47,.92); border:1px solid var(--line); border-radius:10px; padding:12px; font-size:12px; backdrop-filter: blur(6px); }}
.legend {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:6px; margin-top:8px; }}
.dot {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:6px; vertical-align:middle; }}
</style></head>
<body>
<div class=\"top\">
  <span class=\"chip\">Code Atlas Visual</span>
  <span class=\"chip\">center: {safe_symbol}</span>
  <input id=\"search\" class=\"ctl\" placeholder=\"Search node name/id\" style=\"min-width:220px\" />
  <div class=\"filters\">
    <label><input type=\"checkbox\" class=\"etype\" value=\"CALLS\" checked /> CALLS</label>
    <label><input type=\"checkbox\" class=\"etype\" value=\"IMPORTS\" checked /> IMPORTS</label>
    <label><input type=\"checkbox\" class=\"etype\" value=\"CONTAINS\" checked /> CONTAINS</label>
    <label><input type=\"checkbox\" class=\"etype\" value=\"INHERITS\" checked /> INHERITS</label>
  </div>
  <button id=\"fit\" class=\"ctl btn\">Fit</button>
  <button id=\"pause\" class=\"ctl btn\">Pause</button>
  <button id=\"reset\" class=\"ctl btn\">Reset</button>
</div>
<svg id=\"view\"></svg>
<div class=\"panel\" id=\"panel\">
  <strong>Hover node to inspect details.</strong>
  <div id=\"counts\" style=\"margin-top:8px;color:var(--muted)\"></div>
  <div class=\"legend\" id=\"legend\"></div>
</div>

<script>
const data={payload};
const svg=document.getElementById('view'), NS='http://www.w3.org/2000/svg';
const panel=document.getElementById('panel'), counts=document.getElementById('counts');
const search=document.getElementById('search');
const fitBtn=document.getElementById('fit'), pauseBtn=document.getElementById('pause'), resetBtn=document.getElementById('reset');
let W=window.innerWidth,H=window.innerHeight-66,scale=1,ox=0,oy=0,paused=false;
const g=document.createElementNS(NS,'g'); svg.appendChild(g);
const colors={{module:'#5cc8ff',class:'#f9c74f',function:'#90be6d',method:'#43aa8b',symbol:'#b388eb',file:'#f9844a',repo:'#f94144'}};

const nodes=data.nodes.map((n,i)=>({{...n,x:W/2+Math.cos(i*.618)*(80+(i%12)*18),y:H/2+Math.sin(i*.618)*(80+(i%12)*18),vx:0,vy:0,active:false}}));
const byId=Object.fromEntries(nodes.map(n=>[n.id,n]));
const allLinks=data.edges.map(e=>({{...e,source:byId[e.source],target:byId[e.target]}})).filter(e=>e.source&&e.target);

function selectedEdgeTypes(){{
  return new Set(Array.from(document.querySelectorAll('.etype')).filter(c=>c.checked).map(c=>c.value));
}}
function filteredLinks(){{
  const allowed=selectedEdgeTypes();
  return allLinks.filter(e=>allowed.has(e.type));
}}
function renderLegend(){{
  const box=document.getElementById('legend'); box.innerHTML='';
  Object.entries(colors).forEach(([k,v])=>{{
    const d=document.createElement('div'); d.innerHTML=`<span class=\"dot\" style=\"background:${{v}}\"></span>${{k}}`; box.appendChild(d);
  }});
}}

function draw(){{
  while(g.firstChild) g.removeChild(g.firstChild);
  const links=filteredLinks();
  const q=search.value.trim().toLowerCase();
  let visibleNodes=0;
  for(const e of links){{
    const l=document.createElementNS(NS,'line');
    l.setAttribute('class','edge');
    l.setAttribute('x1',e.source.x); l.setAttribute('y1',e.source.y);
    l.setAttribute('x2',e.target.x); l.setAttribute('y2',e.target.y);
    l.setAttribute('stroke-width',e.type==='CALLS'?1.7:1.1);
    l.setAttribute('stroke',e.confidence==='high'?'#6ee7b7':(e.confidence==='low'?'#fca5a5':'#93c5fd'));
    g.appendChild(l);
  }}

  for(const n of nodes){{
    const match=!q||n.label.toLowerCase().includes(q)||n.id.toLowerCase().includes(q);
    if(!match) continue;
    visibleNodes++;
    const grp=document.createElementNS(NS,'g'); grp.setAttribute('class','node'); grp.setAttribute('transform',`translate(${{n.x}},${{n.y}})`);
    const c=document.createElementNS(NS,'circle');
    c.setAttribute('r',n.type==='symbol'?8:11);
    c.setAttribute('fill',colors[n.type]||'#9aa5c8');
    c.setAttribute('stroke',n.active?'#ffffff':'#0f172a');
    c.setAttribute('stroke-width',n.active?'2.8':'1.4');
    grp.appendChild(c);
    const t=document.createElementNS(NS,'text'); t.setAttribute('x','14'); t.setAttribute('y','4'); t.textContent=n.label; grp.appendChild(t);
    grp.addEventListener('mouseenter',()=>{{panel.innerHTML=`<strong>${{n.label}}</strong><br/>Type: ${{n.type}}<br/>Language: ${{n.language||'-'}}<br/>ID: ${{n.id}}<br/>File: ${{n.file||'-'}}<div id='counts' style='margin-top:8px;color:var(--muted)'></div><div class='legend' id='legend'></div>`; renderLegend(); updateCounts();}});
    grp.addEventListener('click',()=>{{nodes.forEach(x=>x.active=false); n.active=true;}});
    enableDrag(grp,n); g.appendChild(grp);
  }}
  g.setAttribute('transform',`translate(${{ox}},${{oy}}) scale(${{scale}})`);
  updateCounts(links.length,visibleNodes);
}}

function updateCounts(edgeCount, nodeCount){{
  const ec=edgeCount??filteredLinks().length; const nc=nodeCount??nodes.length;
  const c=document.getElementById('counts'); if(c) c.innerHTML=`Nodes: <strong>${{nc}}</strong> | Edges: <strong>${{ec}}</strong> | Zoom: <strong>${{scale.toFixed(2)}}x</strong>`;
}}

function physics(){{
  if(paused) return;
  const links=filteredLinks();
  for(const n of nodes){{ n.vx*=0.92; n.vy*=0.92; }}
  for(let i=0;i<nodes.length;i++) for(let j=i+1;j<nodes.length;j++){{
    const a=nodes[i],b=nodes[j]; let dx=b.x-a.x,dy=b.y-a.y,d2=dx*dx+dy*dy+0.01,f=1400/d2;
    a.vx-=f*dx*0.0008; a.vy-=f*dy*0.0008; b.vx+=f*dx*0.0008; b.vy+=f*dy*0.0008;
  }}
  for(const e of links){{
    const dx=e.target.x-e.source.x,dy=e.target.y-e.source.y,dist=Math.sqrt(dx*dx+dy*dy)||1,p=(dist-110)*0.002,fx=(dx/dist)*p,fy=(dy/dist)*p;
    e.source.vx+=fx; e.source.vy+=fy; e.target.vx-=fx; e.target.vy-=fy;
  }}
  for(const n of nodes){{ n.x+=n.vx; n.y+=n.vy; }}
}}

function tick(){{ physics(); draw(); requestAnimationFrame(tick); }}
function enableDrag(el,n){{ let d=false; el.addEventListener('mousedown',e=>{{d=true; e.preventDefault();}}); window.addEventListener('mouseup',()=>d=false); window.addEventListener('mousemove',e=>{{if(!d)return; n.x=(e.clientX-ox)/scale; n.y=(e.clientY-66-oy)/scale; n.vx=0; n.vy=0;}}); }}
function fit(){{
  const minX=Math.min(...nodes.map(n=>n.x)), maxX=Math.max(...nodes.map(n=>n.x));
  const minY=Math.min(...nodes.map(n=>n.y)), maxY=Math.max(...nodes.map(n=>n.y));
  const gw=Math.max(maxX-minX,1), gh=Math.max(maxY-minY,1);
  scale=Math.max(0.25, Math.min(2.8, Math.min((W*0.8)/gw,(H*0.8)/gh))); ox=W/2-((minX+maxX)/2)*scale; oy=H/2-((minY+maxY)/2)*scale;
}}
function reset(){{ search.value=''; document.querySelectorAll('.etype').forEach(c=>c.checked=true); paused=false; pauseBtn.textContent='Pause'; nodes.forEach(n=>n.active=false); fit(); }}

svg.addEventListener('wheel',e=>{{e.preventDefault(); const dir=e.deltaY>0?0.92:1.08; scale=Math.max(.25,Math.min(2.8,scale*dir));}});
let panning=false,sx=0,sy=0;
svg.addEventListener('mousedown',e=>{{ if(e.target.tagName.toLowerCase()!=='svg') return; panning=true; sx=e.clientX-ox; sy=e.clientY-oy; }});
window.addEventListener('mouseup',()=>panning=false);
window.addEventListener('mousemove',e=>{{ if(!panning) return; ox=e.clientX-sx; oy=e.clientY-sy; }});
window.addEventListener('resize',()=>{{ W=window.innerWidth; H=window.innerHeight-66; }});

document.querySelectorAll('.etype').forEach(el=>el.addEventListener('change',draw));
search.addEventListener('input',draw);
fitBtn.addEventListener('click',fit);
pauseBtn.addEventListener('click',()=>{{ paused=!paused; pauseBtn.textContent=paused?'Resume':'Pause'; }});
resetBtn.addEventListener('click',reset);

renderLegend(); fit(); tick();
</script></body></html>"""
