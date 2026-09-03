from __future__ import annotations

"""
Indexing Orchestration Module

This module is the heart of Saurix's indexing engine. It defines the RepositoryIndexer
class, which manages the lifecycle of repository scanning, file language detection,
and dispatching work to language-specific extractors.
"""

import logging
from pathlib import Path
from collections.abc import Callable

from .graph import GraphStore
from .models import Node
from ..infra.config import config
from ..infra.logging import get_logger

logger = get_logger(__name__)

# Map file extensions to language identifiers used for extractor dispatch
# Only languages with real Extractors are listed; others are skipped
LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "typescript",
    ".mjs": "typescript",
    ".cjs": "typescript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
}


def detect_language(path: Path) -> str | None:
    """Returns the normalized language name based on the file extension."""
    return LANGUAGE_BY_EXTENSION.get(path.suffix.lower())


class IndexResult:
    """Container for the results of an indexing operation."""
    def __init__(self, graph: GraphStore, scanned_files: int, indexed_files: int) -> None:
        self.graph = graph
        self.scanned_files = scanned_files
        self.indexed_files = indexed_files


class RepositoryIndexer:
    """
    Orchestrates the process of turning a local directory into a GraphStore.

    Responsibilities:
    - Recursively scanning the repository root for source files.
    - Filtering files based on exclusion lists (e.g., .git, node_modules).
    - Mapping files to appropriate Extractor implementations.
    - Merging partial graphs from individual files into the global GraphStore.
    """
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
        # Lazy import to avoid circular init between core and analysis
        from ..analysis.go_extractor import GoExtractor
        from ..analysis.java_extractor import JavaExtractor
        from ..analysis.python_extractor import PythonExtractor
        from ..analysis.typescript_extractor import TypeScriptExtractor

        # Pre-initialize heavy-weight extractors
        self.extractors = {
            "python": PythonExtractor(),
            "typescript": TypeScriptExtractor(),
            "go": GoExtractor(),
            "java": JavaExtractor(),
        }

    def _scan_files(self) -> list[Path]:
        """Collects all indexable files while respecting exclusion rules."""
        files: list[Path] = []
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(self.root)
            # Skip files in excluded directories
            if any(part in self.exclude_dirs for part in rel.parts):
                continue
            # Only index files with recognized extensions
            if detect_language(path) is None:
                continue
            files.append(path)
        return sorted(files)

    def index(self) -> IndexResult:
        """
        Executes the indexing pipeline.

        Straight scan, dispatch each file to its Extractor, merge into the
        Graph, and write. No cache file is read or written.
        """
        files = self._scan_files()

        # Initialize the graph with a root repository node
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

        total_files = len(files)
        for i, file_path in enumerate(files):
            lang = detect_language(file_path)
            if lang is None:
                continue

            rel = file_path.relative_to(self.root).as_posix()
            files_by_language[lang] = files_by_language.get(lang, 0) + 1

            extractor = self.extractors.get(lang)
            if extractor is None:
                continue
            # Identify which parsing strategy is actually being used
            parser_mode = "ast" if lang == "python" else (
                "tree-sitter" if getattr(extractor, "_parser", None) else "regex-fallback"
            )

            temp_graph = GraphStore()
            try:
                extractor.extract(repo_root=self.root, file_path=file_path, graph=temp_graph)
                # Merge temp graph into main graph
                for node in temp_graph.nodes.values():
                    self.graph.add_node(node)
                for edge in temp_graph.edges:
                    self.graph.add_edge(edge)

                indexed += 1
                indexed_by_language[lang] = indexed_by_language.get(lang, 0) + 1
                parser_mode_by_language[lang] = parser_mode
            except Exception as e:
                logger.error(f"Failed to extract {rel}: {e}")

            if self.on_progress:
                self.on_progress(i + 1, total_files, rel)

        # Record metrics for the stats panel
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

        self.graph.set_metadata("extraction_coverage", coverage)

        return IndexResult(graph=self.graph, scanned_files=len(files), indexed_files=indexed)


def build_graph(
    repo_root: Path,
    exclude_dirs: set[str] | None = None,
    on_file_indexed: Callable[[int, int, str], None] | None = None,
) -> IndexResult:
    """Legacy entrypoint for starting a full repository index."""
    indexer = RepositoryIndexer(repo_root, exclude_dirs, on_file_indexed)
    return indexer.index()
