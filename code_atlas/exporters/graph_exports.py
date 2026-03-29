from __future__ import annotations

import csv
import html
from pathlib import Path

from ..graph import GraphStore


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

    with out_path.open("w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<graphml xmlns="http://graphml.graphdrawing.org/xmlns">\n')

        for idx, (name, typ) in enumerate(node_keys):
            f.write(f'  <key id="n{idx}" for="node" attr.name="{name}" attr.type="{typ}"/>\n')
        for idx, (name, typ) in enumerate(edge_keys):
            f.write(f'  <key id="e{idx}" for="edge" attr.name="{name}" attr.type="{typ}"/>\n')

        f.write('  <graph id="G" edgedefault="directed">\n')
        for node in graph.nodes.values():
            f.write(f'    <node id="{html.escape(str(node.id), quote=True)}">\n')
            values = [node.type, node.language, node.name, node.file or "", node.line or ""]
            for idx, value in enumerate(values):
                f.write(f'      <data key="n{idx}">{html.escape(str(value), quote=True)}</data>\n')
            f.write("    </node>\n")

        for i, edge in enumerate(graph.edges):
            source = html.escape(str(edge.source), quote=True)
            target = html.escape(str(edge.target), quote=True)
            f.write(f'    <edge id="edge_{i}" source="{source}" target="{target}">\n')
            values = [edge.type, edge.language, edge.confidence, edge.file or "", edge.line or ""]
            for idx, value in enumerate(values):
                f.write(f'      <data key="e{idx}">{html.escape(str(value), quote=True)}</data>\n')
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
