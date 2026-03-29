from __future__ import annotations

from pathlib import Path

from .extractors import GoExtractor, PythonExtractor, StubExtractor, TypeScriptExtractor
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

    extractors = {
        "python": PythonExtractor(),
        "typescript": TypeScriptExtractor(),
        "go": GoExtractor(),
    }
    indexed = 0
    files_by_language: dict[str, int] = {}
    indexed_by_language: dict[str, int] = {}
    parser_mode_by_language: dict[str, str] = {}

    for file_path in files:
        lang = detect_language(file_path)
        if lang is None:
            continue
        files_by_language[lang] = files_by_language.get(lang, 0) + 1

        extractor = extractors.get(lang)
        if extractor is not None:
            extractor.extract(repo_root=root, file_path=file_path, graph=graph)
            indexed += 1
            indexed_by_language[lang] = indexed_by_language.get(lang, 0) + 1
            parser_mode = "ast" if lang == "python" else ("tree-sitter" if getattr(extractor, "_parser", None) else "regex-fallback")
            parser_mode_by_language[lang] = parser_mode
        else:
            StubExtractor(lang).extract(repo_root=root, file_path=file_path, graph=graph)
            indexed += 1
            indexed_by_language[lang] = indexed_by_language.get(lang, 0) + 1
            parser_mode_by_language[lang] = "stub"

    coverage: dict[str, dict[str, object]] = {}
    for lang, total in sorted(files_by_language.items()):
        indexed_count = indexed_by_language.get(lang, 0)
        pct = round((indexed_count / total) * 100, 2) if total else 0.0
        coverage[lang] = {
            "files_seen": total,
            "files_indexed": indexed_count,
            "coverage_percent": pct,
            "parser_mode": parser_mode_by_language.get(lang, "unknown"),
        }

    graph.set_metadata("extraction_coverage", coverage)

    return IndexResult(graph=graph, scanned_files=len(files), indexed_files=indexed)
