"""
Tests for grammar acquisition.

Every supported language extracts through tree-sitter, from a maintained
grammar bundle, with no regex path left to degrade into and nothing in the
extraction statistics claiming a parsing strategy.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

from saurix.analysis.tree_sitter_support import GrammarUnavailableError, get_parser
from saurix.core.indexing import build_graph

REPO_ROOT = Path(__file__).resolve().parent.parent

TREE_SITTER_LANGUAGES = ("typescript", "go", "java")
ALL_LANGUAGES = ("python", *TREE_SITTER_LANGUAGES)


def _declared_dependencies() -> list[str]:
    """
    Read the runtime dependencies as written in the package metadata.
    """
    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    return pyproject["project"]["dependencies"]


def _package_name(requirement: str) -> str:
    """
    Return the distribution name a requirement string pins.
    """
    return requirement.split(">")[0].split("=")[0].split("<")[0].strip()


@pytest.fixture
def polyglot_repo(tmp_path: Path) -> Path:
    """
    A repository holding one file per supported language.
    """
    (tmp_path / "a.py").write_text(
        "def f():\n    return g()\n\ndef g():\n    return 1\n"
    )
    (tmp_path / "b.ts").write_text(
        'import { g } from "pkg-a";\nexport function f() { return g(); }\n'
    )
    (tmp_path / "c.go").write_text(
        'package c\n\nimport "fmt"\n\nfunc F() { fmt.Println(g()) }\n\nfunc g() {}\n'
    )
    (tmp_path / "D.java").write_text(
        "package d;\nimport java.util.List;\n"
        "public class D { void f() { g(); } void g() {} }\n"
    )
    return tmp_path


class TestGrammarDependencies:
    """
    Grammars come from a maintained package, and the archived one is gone.
    """

    def test_archived_grammar_bundle_is_not_a_dependency(self) -> None:
        """
        tree-sitter-languages is no longer declared.
        """
        names = [_package_name(req) for req in _declared_dependencies()]

        assert "tree-sitter-languages" not in names

    def test_maintained_grammar_bundle_is_a_dependency(self) -> None:
        """
        tree-sitter-language-pack is declared, since every tree-sitter grammar
        Saurix uses comes from it.
        """
        names = [_package_name(req) for req in _declared_dependencies()]

        assert "tree-sitter-language-pack" in names


class TestGrammarAcquisition:
    """
    A grammar is built for every language, or the tool says why it cannot.
    """

    @pytest.mark.parametrize("language", TREE_SITTER_LANGUAGES)
    def test_grammar_parses(self, language: str) -> None:
        """
        Each tree-sitter grammar loads and parses.
        """
        parser = get_parser(language)

        assert parser.parse(b"x").root_node is not None

    def test_archived_bundle_is_never_imported(self) -> None:
        """
        Building a parser pulls in the maintained bundle only, so nothing is
        running on top of the archived one.
        """
        for language in TREE_SITTER_LANGUAGES:
            get_parser(language)

        assert "tree_sitter_languages" not in sys.modules

    def test_unavailable_grammar_reports_itself(self) -> None:
        """
        An unknown language raises a named error naming the language, rather
        than returning nothing and leaving the caller to carry on.
        """
        with pytest.raises(GrammarUnavailableError) as excinfo:
            get_parser("saurix-nonexistent-language")

        assert "saurix-nonexistent-language" in str(excinfo.value)


class TestSingleExtractionPath:
    """
    One path per language, with no second implementation left behind.
    """

    def test_regex_extractor_is_absent(self) -> None:
        """
        saurix.analysis.regex_lang no longer exists, so nothing can reach for a
        regex extraction.
        """
        import importlib.util

        assert importlib.util.find_spec("saurix.analysis.regex_lang") is None


class TestIndexingEveryLanguage:
    """
    Indexing a polyglot repository produces a complete graph.
    """

    def test_no_file_fails_to_extract(self, polyglot_repo: Path) -> None:
        """
        Every scanned file lands in the graph: seen and indexed counts match
        for all four languages.
        """
        result = build_graph(polyglot_repo)

        assert result.scanned_files == 4
        assert result.indexed_files == 4

        coverage = result.graph.stats()["extraction_coverage"]
        assert set(coverage) == set(ALL_LANGUAGES)
        for lang, row in coverage.items():
            assert row["files_seen"] == row["files_indexed"], lang
            assert row["coverage_percent"] == 100.0, lang

    def test_extracted_symbols_come_from_the_syntax_tree(
        self, polyglot_repo: Path
    ) -> None:
        """
        Declarations only a grammar can see reach the graph: a call and an
        import in TypeScript, Go, and Java.
        """
        result = build_graph(polyglot_repo)

        symbols = set(result.graph.symbols)
        assert "typescript://b:f" in symbols
        assert "go://c:g" in symbols

        imports = {
            (e.source, e.target) for e in result.graph.edges if e.type == "IMPORTS"
        }
        assert ("typescript://b", "typescript://pkg-a") in imports
        assert ("go://c", "go://fmt") in imports
        assert ("java://D", "java://java.util.List") in imports

    def test_coverage_reports_no_parsing_strategy(self, polyglot_repo: Path) -> None:
        """
        Coverage rows carry counts only; there is one strategy left, so nothing
        reports which one was taken.
        """
        result = build_graph(polyglot_repo)

        coverage = result.graph.stats()["extraction_coverage"]
        for row in coverage.values():
            assert set(row) == {
                "files_seen",
                "files_indexed",
                "coverage_percent",
            }
