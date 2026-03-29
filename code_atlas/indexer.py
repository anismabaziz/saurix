from __future__ import annotations

"""Index orchestration: scan files, dispatch extractors, and compute coverage."""

from pathlib import Path

from .cache import DEFAULT_CACHE_PATH, deserialize_contribution, file_hash, load_cache, save_cache, serialize_contribution
from .extractors import GoExtractor, JavaExtractor, PythonExtractor, StubExtractor, TypeScriptExtractor
from .graph import GraphStore
from .models import Node
from .scanner import detect_language, scan_source_files


class IndexResult:
    def __init__(self, graph: GraphStore, scanned_files: int, indexed_files: int) -> None:
        self.graph = graph
        self.scanned_files = scanned_files
        self.indexed_files = indexed_files


def build_graph(repo_root: Path) -> IndexResult:
    """Build a graph for a repository root and attach extraction metadata."""
    root = repo_root.resolve()
    files = scan_source_files(root)
    cache_path = (root / DEFAULT_CACHE_PATH).resolve()
    cache = load_cache(cache_path)
    cached_files: dict[str, dict[str, object]] = cache.get("files", {}) if isinstance(cache.get("files"), dict) else {}

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
        "java": JavaExtractor(),
    }
    indexed = 0
    files_by_language: dict[str, int] = {}
    indexed_by_language: dict[str, int] = {}
    parser_mode_by_language: dict[str, str] = {}
    next_cache_files: dict[str, dict[str, object]] = {}
    reused_files = 0
    changed_files = 0

    current_rel_paths = set()

    for file_path in files:
        lang = detect_language(file_path)
        if lang is None:
            continue
        rel = file_path.relative_to(root).as_posix()
        current_rel_paths.add(rel)
        files_by_language[lang] = files_by_language.get(lang, 0) + 1

        extractor = extractors.get(lang)
        parser_mode = "stub"
        if extractor is not None:
            parser_mode = "ast" if lang == "python" else ("tree-sitter" if getattr(extractor, "_parser", None) else "regex-fallback")
        cached = cached_files.get(rel)
        fingerprint = file_hash(file_path)

        if isinstance(cached, dict) and cached.get("hash") == fingerprint and cached.get("lang") == lang and cached.get("parser_mode") == parser_mode:
            nodes, edges = deserialize_contribution(cached)
            for node in nodes:
                graph.add_node(node)
            for edge in edges:
                graph.add_edge(edge)
            next_cache_files[rel] = cached
            reused_files += 1
            indexed += 1
            indexed_by_language[lang] = indexed_by_language.get(lang, 0) + 1
            parser_mode_by_language[lang] = parser_mode
            continue

        changed_files += 1
        if extractor is not None:
            temp_graph = GraphStore()
            extractor.extract(repo_root=root, file_path=file_path, graph=temp_graph)
            for node in temp_graph.nodes.values():
                graph.add_node(node)
            for edge in temp_graph.edges:
                graph.add_edge(edge)

            nodes = list(temp_graph.nodes.values())
            edges = list(temp_graph.edges)
            next_cache_files[rel] = serialize_contribution(
                nodes,
                edges,
                lang=lang,
                fingerprint=fingerprint,
                parser_mode=parser_mode,
            )

            indexed += 1
            indexed_by_language[lang] = indexed_by_language.get(lang, 0) + 1
            parser_mode_by_language[lang] = parser_mode
        else:
            StubExtractor(lang).extract(repo_root=root, file_path=file_path, graph=graph)
            nodes = [n for n in graph.nodes.values() if n.file == rel]
            edges = [e for e in graph.edges if e.file == rel]
            next_cache_files[rel] = serialize_contribution(
                nodes,
                edges,
                lang=lang,
                fingerprint=fingerprint,
                parser_mode="stub",
            )
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
    deleted_files = sorted(set(cached_files.keys()) - current_rel_paths)
    graph.set_metadata(
        "incremental_cache",
        {
            "enabled": True,
            "cache_path": str(cache_path),
            "cache_hits": reused_files,
            "reindexed_files": changed_files,
            "deleted_files": len(deleted_files),
        },
    )

    save_cache(cache_path, next_cache_files)

    return IndexResult(graph=graph, scanned_files=len(files), indexed_files=indexed)
