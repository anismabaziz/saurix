"""
Indexing-level checks: unsupported (stub) languages are skipped and unchanged
files are reused from the incremental cache.

Confirms the simplifications landed in indexing: files without a real Extractor
produce no placeholder Symbols. And confirms incremental indexing: a second run
over an unchanged tree reuses the cached contributions, while changed, added,
deleted, and renamed files are reflected in the Graph.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from saurix.core.cache import DEFAULT_CACHE_PATH
from saurix.core.indexing import build_graph


class TestStubLanguagesSkipped:
    """
    Files without a real Extractor are skipped entirely.
    """

    def test_unsupported_extensions_produce_no_symbols(self, tmp_path: Path) -> None:
        """
        Ruby, Rust, PHP, and C# files are not indexed.
        """
        (tmp_path / "app.rb").write_text("class App\nend\n")
        (tmp_path / "lib.rs").write_text("fn main() {}\n")
        (tmp_path / "index.php").write_text("<?php echo 1;\n")
        (tmp_path / "game.cs").write_text("class Game {}\n")

        result = build_graph(tmp_path)

        assert result.scanned_files == 0
        assert result.indexed_files == 0
        # Only the repo root meta Symbol remains
        assert set(result.graph.symbols) == {f"repo://{tmp_path.name}"}
        assert {n.language for n in result.graph.symbols.values()} == {"meta"}

    def test_stats_hold_no_stub_coverage(self, tmp_path: Path) -> None:
        """
        Graph stats expose no coverage rows for unsupported languages.
        """
        (tmp_path / "app.rb").write_text("class App\nend\n")
        (tmp_path / "app.py").write_text("def f():\n    return 1\n")

        result = build_graph(tmp_path)

        coverage = result.graph.stats()["extraction_coverage"]
        assert set(coverage.keys()) == {"python"}

    def test_supported_languages_indexed(self, tmp_path: Path) -> None:
        """
        Python, TypeScript/JavaScript, Go, and Java fixtures are indexed.
        """
        (tmp_path / "a.py").write_text("def f():\n    return 1\n")
        (tmp_path / "b.ts").write_text("export function g() { return 1; }\n")
        (tmp_path / "c.go").write_text("package c\nfunc H() {}\n")
        (tmp_path / "D.java").write_text("public class D {}\n")

        result = build_graph(tmp_path)

        langs = {n.language for n in result.graph.symbols.values()}
        assert {"python", "typescript", "go", "java"} <= langs


class TestIncrementalCache:
    """
    A second run over an unchanged tree reuses the cache; edits are reflected.
    """

    def _cache_path(self, repo: Path) -> Path:
        """
        The single file holding the incremental cache for a repository.
        """
        return repo / DEFAULT_CACHE_PATH

    def test_first_run_extracts_everything(self, tmp_path: Path) -> None:
        """
        A first run on a fresh checkout extracts every file, reusing nothing.
        """
        (tmp_path / "a.py").write_text("def f():\n    return 1\n")
        (tmp_path / "b.py").write_text("def g():\n    return 2\n")

        result = build_graph(tmp_path)

        assert result.scanned_files == 2
        assert result.indexed_files == 2
        assert result.reused_files == 0
        assert result.reextracted_files == 2

    def test_second_run_reuses_unchanged_files(self, tmp_path: Path) -> None:
        """
        Re-indexing an unchanged repository skips every file and matches the
        first graph exactly.
        """
        (tmp_path / "a.py").write_text("def f():\n    return f()\n")
        (tmp_path / "b.py").write_text("def g():\n    return 1\n")

        first = build_graph(tmp_path)
        second = build_graph(tmp_path)

        assert second.reused_files == 2
        assert second.reextracted_files == 0
        assert second.graph.to_dict() == first.graph.to_dict()

    def test_changed_file_is_reextracted(self, tmp_path: Path) -> None:
        """
        Editing one file re-extracts only that file; the other is reused.
        """
        (tmp_path / "a.py").write_text("def f():\n    return 1\n")
        (tmp_path / "b.py").write_text("def g():\n    return 1\n")
        build_graph(tmp_path)

        (tmp_path / "a.py").write_text(
            "def f():\n    return 1\n\ndef h():\n    return 3\n"
        )
        result = build_graph(tmp_path)

        assert result.reused_files == 1
        assert result.reextracted_files == 1
        names = {symbol.name for symbol in result.graph.symbols.values()}
        assert "h" in names

    def test_added_file_is_extracted(self, tmp_path: Path) -> None:
        """
        A new file is extracted while the existing ones are reused.
        """
        (tmp_path / "a.py").write_text("def f():\n    return 1\n")
        build_graph(tmp_path)

        (tmp_path / "b.py").write_text("def g():\n    return 2\n")
        result = build_graph(tmp_path)

        assert result.reused_files == 1
        assert result.reextracted_files == 1
        assert result.scanned_files == 2

    def test_deleted_file_leaves_no_symbols(self, tmp_path: Path) -> None:
        """
        Symbols and edges from a deleted file are gone after re-indexing.
        """
        (tmp_path / "a.py").write_text("def f():\n    return 1\n")
        (tmp_path / "doomed.py").write_text("def gone():\n    return 0\n")
        build_graph(tmp_path)

        (tmp_path / "doomed.py").unlink()
        result = build_graph(tmp_path)

        files = {symbol.file for symbol in result.graph.symbols.values()}
        assert "doomed.py" not in files
        names = {symbol.name for symbol in result.graph.symbols.values()}
        assert "gone" not in names

    def test_renamed_file_updates_locations(self, tmp_path: Path) -> None:
        """
        Renaming a file moves its symbols to the new path, with no ghosts.
        """
        (tmp_path / "old.py").write_text("def f():\n    return 1\n")
        build_graph(tmp_path)

        (tmp_path / "old.py").rename(tmp_path / "new.py")
        result = build_graph(tmp_path)

        files = {symbol.file for symbol in result.graph.symbols.values()}
        assert "old.py" not in files
        assert "new.py" in files

    def test_cache_is_a_single_file_that_resets_on_delete(self, tmp_path: Path) -> None:
        """
        The cache is one file, and deleting it makes the next run cold.
        """
        (tmp_path / "a.py").write_text("def f():\n    return 1\n")
        build_graph(tmp_path)

        assert self._cache_path(tmp_path).is_file()

        self._cache_path(tmp_path).unlink()
        result = build_graph(tmp_path)

        assert result.reused_files == 0
        assert result.reextracted_files == 1

    def test_cache_from_another_repository_is_discarded(self, tmp_path: Path) -> None:
        """
        A cache file copied from another checkout is rebuilt, not trusted.
        """
        other = tmp_path / "other"
        other.mkdir()
        (other / "a.py").write_text("def f():\n    return 1\n")
        build_graph(other)

        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "a.py").write_text("def f():\n    return 1\n")
        foreign = self._cache_path(other)
        mine = self._cache_path(repo)
        mine.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(foreign, mine)

        result = build_graph(repo)

        assert result.reused_files == 0
        assert result.reextracted_files == 1
        names = {symbol.name for symbol in result.graph.symbols.values()}
        assert "f" in names

    def test_corrupt_cache_is_discarded(self, tmp_path: Path) -> None:
        """
        A cache file that is not valid JSON is rebuilt, not trusted.
        """
        (tmp_path / "a.py").write_text("def f():\n    return 1\n")
        cache = self._cache_path(tmp_path)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text("{ this is not json")

        result = build_graph(tmp_path)

        assert result.reused_files == 0
        assert result.reextracted_files == 1

    def test_stale_extraction_version_is_discarded(self, tmp_path: Path) -> None:
        """
        A cache written by a different extraction version is rebuilt.
        """
        (tmp_path / "a.py").write_text("def f():\n    return 1\n")
        build_graph(tmp_path)

        payload = json.loads(self._cache_path(tmp_path).read_text())
        payload["saurix_version"] = "0.0.0-ancient"
        self._cache_path(tmp_path).write_text(json.dumps(payload))

        result = build_graph(tmp_path)

        assert result.reused_files == 0
        assert result.reextracted_files == 1

    def test_cache_from_another_machine_is_discarded(self, tmp_path: Path) -> None:
        """
        A cache file stamped by another machine is rebuilt, not trusted.
        """
        (tmp_path / "a.py").write_text("def f():\n    return 1\n")
        build_graph(tmp_path)

        payload = json.loads(self._cache_path(tmp_path).read_text())
        payload["host_id"] = "some-other-machine"
        self._cache_path(tmp_path).write_text(json.dumps(payload))

        result = build_graph(tmp_path)

        assert result.reused_files == 0
        assert result.reextracted_files == 1

    def test_reindex_matches_a_cold_index_after_edits(self, tmp_path: Path) -> None:
        """
        After edits and a deletion, the reused graph equals a fresh index of
        the same tree: no ghosts in symbols or edges.
        """
        (tmp_path / "keep.py").write_text("def stay():\n    return 1\n")
        (tmp_path / "change.py").write_text("def old():\n    return 1\n")
        (tmp_path / "doomed.py").write_text("def gone():\n    return 0\n")
        build_graph(tmp_path)

        (tmp_path / "change.py").write_text("def new():\n    return 2\n")
        (tmp_path / "doomed.py").unlink()
        (tmp_path / "added.py").write_text("def fresh():\n    return 3\n")
        result = build_graph(tmp_path)

        pristine = tmp_path / "pristine"
        pristine.mkdir()
        for name in ("keep.py", "change.py", "added.py"):
            shutil.copy(tmp_path / name, pristine / name)
        cold = build_graph(pristine)

        assert self._without_repo_root(
            result.graph.to_dict()
        ) == self._without_repo_root(cold.graph.to_dict())

    @staticmethod
    def _without_repo_root(graph_dict: dict[str, object]) -> dict[str, object]:
        """
        Drop the repository root symbol, which names its own directory.
        """
        symbols = [
            symbol
            for symbol in graph_dict["symbols"]
            if not symbol["id"].startswith("repo://")
        ]
        return {**graph_dict, "symbols": symbols}
