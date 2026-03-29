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
:root {{ --bg:#0b1020; --text:#dce6ff; --muted:#8ea2c9; --accent:#4fd1c5; }}
body {{ margin:0; font-family:ui-monospace,Menlo,Consolas,monospace; background:radial-gradient(1200px 800px at 20% -10%,#1a2a52,var(--bg)); color:var(--text); }}
.top {{ padding:14px 18px; border-bottom:1px solid #273555; }}
.top h1 {{ margin:0; font-size:15px; }} .top p {{ margin:6px 0 0; color:var(--muted); font-size:12px; }}
svg {{ width:100vw; height:calc(100vh - 74px); display:block; }} .node text {{ font-size:11px; fill:var(--text); pointer-events:none; }}
.edge {{ stroke:#6f86b5; stroke-opacity:.55; }}
.tip {{ position:fixed; right:14px; top:84px; width:300px; background:rgba(17,24,45,.92); border:1px solid #304066; border-radius:10px; padding:12px; font-size:12px; }}
</style></head>
<body><div class=\"top\"><h1>Code Atlas Visual Subgraph</h1><p>Centered on: <strong>{safe_symbol}</strong></p></div>
<svg id=\"view\"></svg><div class=\"tip\" id=\"tip\">Hover node to inspect details.</div>
<script>
const data={payload};const W=window.innerWidth,H=window.innerHeight-74,svg=document.getElementById('view'),NS='http://www.w3.org/2000/svg',tip=document.getElementById('tip');
let scale=1,ox=0,oy=0;const g=document.createElementNS(NS,'g');svg.appendChild(g);
const nodes=data.nodes.map((n,i)=>({{...n,x:W/2+Math.cos(i*.618)*(80+(i%12)*18),y:H/2+Math.sin(i*.618)*(80+(i%12)*18),vx:0,vy:0}}));
const byId=Object.fromEntries(nodes.map(n=>[n.id,n]));const links=data.edges.map(e=>({{...e,source:byId[e.source],target:byId[e.target]}})).filter(e=>e.source&&e.target);
const color=t=>({{module:'#5cc8ff',class:'#f9c74f',function:'#90be6d',method:'#43aa8b',symbol:'#b388eb',file:'#f9844a',repo:'#f94144'}}[t]||'#9aa5c8');
function draw(){{while(g.firstChild)g.removeChild(g.firstChild);for(const e of links){{const l=document.createElementNS(NS,'line');l.setAttribute('class','edge');l.setAttribute('x1',e.source.x);l.setAttribute('y1',e.source.y);l.setAttribute('x2',e.target.x);l.setAttribute('y2',e.target.y);l.setAttribute('stroke-width',e.type==='CALLS'?1.6:1.1);g.appendChild(l);}}
for(const n of nodes){{const k=document.createElementNS(NS,'g');k.setAttribute('class','node');k.setAttribute('transform',`translate(${{n.x}},${{n.y}})`);const c=document.createElementNS(NS,'circle');c.setAttribute('r',n.type==='symbol'?8:11);c.setAttribute('fill',color(n.type));c.setAttribute('stroke','#0f172a');c.setAttribute('stroke-width','1.4');k.appendChild(c);const t=document.createElementNS(NS,'text');t.setAttribute('x','14');t.setAttribute('y','4');t.textContent=n.label;k.appendChild(t);k.addEventListener('mouseenter',()=>{{tip.innerHTML=`<strong>${{n.label}}</strong><br/>Type: ${{n.type}}<br/>ID: ${{n.id}}<br/>File: ${{n.file||'-'}}`;}});drag(k,n);g.appendChild(k);}}
g.setAttribute('transform',`translate(${{ox}},${{oy}}) scale(${{scale}})`);}}
function tick(){{for(const n of nodes){{n.vx*=.92;n.vy*=.92;}}for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){{const a=nodes[i],b=nodes[j];let dx=b.x-a.x,dy=b.y-a.y,d2=dx*dx+dy*dy+.01,f=1400/d2;a.vx-=f*dx*.0008;a.vy-=f*dy*.0008;b.vx+=f*dx*.0008;b.vy+=f*dy*.0008;}}
for(const e of links){{const dx=e.target.x-e.source.x,dy=e.target.y-e.source.y,dist=Math.sqrt(dx*dx+dy*dy)||1,p=(dist-110)*.002,fx=(dx/dist)*p,fy=(dy/dist)*p;e.source.vx+=fx;e.source.vy+=fy;e.target.vx-=fx;e.target.vy-=fy;}}
for(const n of nodes){{n.x+=n.vx;n.y+=n.vy;}}draw();requestAnimationFrame(tick);}}
function drag(el,n){{let d=false;el.addEventListener('mousedown',e=>{{d=true;e.preventDefault();}});window.addEventListener('mouseup',()=>d=false);window.addEventListener('mousemove',e=>{{if(!d)return;n.x=(e.clientX-ox)/scale;n.y=(e.clientY-74-oy)/scale;n.vx=0;n.vy=0;}});}}
svg.addEventListener('wheel',e=>{{e.preventDefault();const dir=e.deltaY>0?.92:1.08;scale=Math.max(.25,Math.min(2.8,scale*dir));}});
let pan=false,sx=0,sy=0;svg.addEventListener('mousedown',e=>{{if(e.target.tagName.toLowerCase()!=='svg')return;pan=true;sx=e.clientX-ox;sy=e.clientY-oy;}});window.addEventListener('mouseup',()=>pan=false);window.addEventListener('mousemove',e=>{{if(!pan)return;ox=e.clientX-sx;oy=e.clientY-sy;}});tick();
</script></body></html>"""
