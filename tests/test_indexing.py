"""Indexing-level checks: unsupported (stub) languages are skipped and no cache is written.

Confirms the simplifications landed in indexing: files without a real Extractor
produce no placeholder Symbols, and indexing is a straight scan that never
creates or replays a cache file.
"""

from __future__ import annotations

from pathlib import Path

from saurix.core.indexing import build_graph


class TestStubLanguagesSkipped:
    """Files without a real Extractor are skipped entirely."""

    def test_unsupported_extensions_produce_no_symbols(self, tmp_path: Path) -> None:
        """Ruby, Rust, PHP, and C# files are not indexed."""
        (tmp_path / "app.rb").write_text("class App\nend\n")
        (tmp_path / "lib.rs").write_text("fn main() {}\n")
        (tmp_path / "index.php").write_text("<?php echo 1;\n")
        (tmp_path / "game.cs").write_text("class Game {}\n")

        result = build_graph(tmp_path)

        assert result.scanned_files == 0
        assert result.indexed_files == 0
        # Only the repo root meta node remains
        assert set(result.graph.nodes) == {f"repo://{tmp_path.name}"}
        assert {n.language for n in result.graph.nodes.values()} == {"meta"}

    def test_stats_hold_no_stub_coverage(self, tmp_path: Path) -> None:
        """Graph stats expose no coverage rows for unsupported languages."""
        (tmp_path / "app.rb").write_text("class App\nend\n")
        (tmp_path / "app.py").write_text("def f():\n    return 1\n")

        result = build_graph(tmp_path)

        coverage = result.graph.stats()["extraction_coverage"]
        assert set(coverage.keys()) == {"python"}

    def test_supported_languages_indexed(self, tmp_path: Path) -> None:
        """Python, TypeScript/JavaScript, Go, and Java fixtures are indexed."""
        (tmp_path / "a.py").write_text("def f():\n    return 1\n")
        (tmp_path / "b.ts").write_text("export function g() { return 1; }\n")
        (tmp_path / "c.go").write_text("package c\nfunc H() {}\n")
        (tmp_path / "D.java").write_text("public class D {}\n")

        result = build_graph(tmp_path)

        langs = {n.language for n in result.graph.nodes.values()}
        assert {"python", "typescript", "go", "java"} <= langs


class TestNoCache:
    """Indexing is a straight scan with no cache file written or replayed."""

    def test_no_cache_file_created(self, tmp_path: Path) -> None:
        """No cache artifact appears anywhere under the repo."""
        (tmp_path / "m.py").write_text("def f():\n    return 1\n")

        build_graph(tmp_path)

        caches = [p for p in tmp_path.rglob("*") if "cache" in p.name.lower()]
        assert caches == []

    def test_reindex_produces_identical_graph(self, tmp_path: Path) -> None:
        """Re-running the index from scratch yields the same graph twice."""
        (tmp_path / "m.py").write_text("def f():\n    return f()\n")

        first = build_graph(tmp_path)
        second = build_graph(tmp_path)

        assert first.graph.to_dict() == second.graph.to_dict()

    def test_stats_hold_no_cache_section(self, tmp_path: Path) -> None:
        """The stats dictionary exposes no cache-specific keys."""
        (tmp_path / "m.py").write_text("def f():\n    return 1\n")

        result = build_graph(tmp_path)

        keys = " ".join(result.graph.stats().keys()).lower()
        assert "cache" not in keys