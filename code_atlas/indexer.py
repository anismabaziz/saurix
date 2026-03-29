from __future__ import annotations

from pathlib import Path

from .extractors import PythonExtractor, StubExtractor
from .graph import GraphStore
from .models import Node
from .scanner import detect_language, scan_source_files


class IndexResult:
    def __init__(self, graph: GraphStore, scanned_files: int, indexed_files: int) -> None:
        self.graph = graph
        self.scanned_files = scanned_files
        self.indexed_files = indexed_files


def build_graph(repo_root: Path) -> IndexResult:
    root = repo_root.resolve()
    files = scan_source_files(root)
    graph = GraphStore()

    graph.add_node(
        Node(
            id=f"repo://{root.name}",
            type="repo",
            language="meta",
            name=root.name,
            file=".",
        )
    )

    python_extractor = PythonExtractor()
    indexed = 0

    for file_path in files:
        lang = detect_language(file_path)
        if lang is None:
            continue

        if lang == "python":
            python_extractor.extract(repo_root=root, file_path=file_path, graph=graph)
            indexed += 1
        else:
            StubExtractor(lang).extract(repo_root=root, file_path=file_path, graph=graph)
            indexed += 1

    return IndexResult(graph=graph, scanned_files=len(files), indexed_files=indexed)
