from __future__ import annotations

"""Index orchestration: scan files, dispatch extractors, and compute coverage."""

import logging
from pathlib import Path
from collections.abc import Callable
from typing import Any

from .cache import DEFAULT_CACHE_PATH, deserialize_contribution, file_hash, load_cache, save_cache, serialize_contribution
from .graph import GraphStore
from .models import Node
from ..analysis import GoExtractor, JavaExtractor, PythonExtractor, StubExtractor, TypeScriptExtractor
from ..infra.config import config
from ..infra.logging import get_logger

logger = get_logger(__name__)

LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".kt": "kotlin",
    ".swift": "swift",
}


def detect_language(path: Path) -> str | None:
    return LANGUAGE_BY_EXTENSION.get(path.suffix.lower())


class IndexResult:
    def __init__(self, graph: GraphStore, scanned_files: int, indexed_files: int) -> None:
        self.graph = graph
        self.scanned_files = scanned_files
        self.indexed_files = indexed_files


class RepositoryIndexer:
    def __init__(
        self,
        repo_root: Path,
        exclude_dirs: set[str] | None = None,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> None:
        self.root = repo_root.resolve()
        self.exclude_dirs = exclude_dirs or config.exclude_dirs
        self.on_progress = on_progress
        self.graph = GraphStore()
        self.extractors = {
            "python": PythonExtractor(),
            "typescript": TypeScriptExtractor(),
            "go": GoExtractor(),
            "java": JavaExtractor(),
        }

    def _scan_files(self) -> list[Path]:
        files: list[Path] = []
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(self.root)
            if any(part in self.exclude_dirs for part in rel.parts):
                continue
            if detect_language(path) is None:
                continue
            files.append(path)
        return sorted(files)

    def index(self) -> IndexResult:
        """Execute the indexing pipeline."""
        files = self._scan_files()
        cache_path = (self.root / DEFAULT_CACHE_PATH).resolve()
        cache = load_cache(cache_path)
        cached_files: dict[str, dict[str, Any]] = cache.get("files", {}) if isinstance(cache.get("files"), dict) else {}

        # Add root node
        self.graph.add_node(
            Node(
                id=f"repo://{self.root.name}",
                type="repo",
                language="meta",
                name=self.root.name,
                file=".",
            )
        )

        indexed = 0
        files_by_language: dict[str, int] = {}
        indexed_by_language: dict[str, int] = {}
        parser_mode_by_language: dict[str, str] = {}
        next_cache_files: dict[str, dict[str, Any]] = {}
        reused_files = 0
        changed_files = 0
        current_rel_paths = set()

        total_files = len(files)
        for i, file_path in enumerate(files):
            lang = detect_language(file_path)
            if lang is None:
                continue
            
            rel = file_path.relative_to(self.root).as_posix()
            current_rel_paths.add(rel)
            files_by_language[lang] = files_by_language.get(lang, 0) + 1

            extractor = self.extractors.get(lang)
            parser_mode = "stub"
            if extractor is not None:
                # Determine parser mode for metadata
                parser_mode = "ast" if lang == "python" else (
                    "tree-sitter" if getattr(extractor, "_parser", None) else "regex-fallback"
                )
            
            cached = cached_files.get(rel)
            fingerprint = file_hash(file_path)

            # Try cache hit
            if (isinstance(cached, dict) and 
                cached.get("hash") == fingerprint and 
                cached.get("lang") == lang and 
                cached.get("parser_mode") == parser_mode):
                
                nodes, edges = deserialize_contribution(cached)
                for node in nodes:
                    self.graph.add_node(node)
                for edge in edges:
                    self.graph.add_edge(edge)
                
                next_cache_files[rel] = cached
                reused_files += 1
                indexed += 1
                indexed_by_language[lang] = indexed_by_language.get(lang, 0) + 1
                parser_mode_by_language[lang] = parser_mode
                if self.on_progress:
                    self.on_progress(i + 1, total_files, rel)
                continue

            # Cache miss or change
            changed_files += 1
            if extractor is not None:
                temp_graph = GraphStore()
                try:
                    extractor.extract(repo_root=self.root, file_path=file_path, graph=temp_graph)
                    for node in temp_graph.nodes.values():
                        self.graph.add_node(node)
                    for edge in temp_graph.edges:
                        self.graph.add_edge(edge)

                    next_cache_files[rel] = serialize_contribution(
                        list(temp_graph.nodes.values()),
                        list(temp_graph.edges),
                        lang=lang,
                        fingerprint=fingerprint,
                        parser_mode=parser_mode,
                    )
                    indexed += 1
                    indexed_by_language[lang] = indexed_by_language.get(lang, 0) + 1
                    parser_mode_by_language[lang] = parser_mode
                except Exception as e:
                    logger.error(f"Failed to extract {rel}: {e}")
            else:
                # Fallback to stub
                StubExtractor(lang).extract(repo_root=self.root, file_path=file_path, graph=self.graph)
                nodes = [n for n in self.graph.nodes.values() if n.file == rel]
                edges = [e for e in self.graph.edges if e.file == rel]
                next_cache_files[rel] = serialize_contribution(
                    nodes, edges, lang=lang, fingerprint=fingerprint, parser_mode="stub"
                )
                indexed += 1
                indexed_by_language[lang] = indexed_by_language.get(lang, 0) + 1
                parser_mode_by_language[lang] = "stub"

            if self.on_progress:
                self.on_progress(i + 1, total_files, rel)

        # Finalize metadata
        coverage: dict[str, dict[str, Any]] = {}
        for lang, total in sorted(files_by_language.items()):
            indexed_count = indexed_by_language.get(lang, 0)
            pct = round((indexed_count / total) * 100, 2) if total else 0.0
            coverage[lang] = {
                "files_seen": total,
                "files_indexed": indexed_count,
                "coverage_percent": pct,
                "parser_mode": parser_mode_by_language.get(lang, "unknown"),
            }

        self.graph.set_metadata("extraction_coverage", coverage)
        deleted_files = sorted(set(cached_files.keys()) - current_rel_paths)
        self.graph.set_metadata(
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
        return IndexResult(graph=self.graph, scanned_files=len(files), indexed_files=indexed)


def build_graph(
    repo_root: Path,
    exclude_dirs: set[str] | None = None,
    on_file_indexed: Callable[[int, int, str], None] | None = None,
) -> IndexResult:
    """Legacy wrapper for build_graph to maintain compatibility."""
    indexer = RepositoryIndexer(repo_root, exclude_dirs, on_file_indexed)
    return indexer.index()
