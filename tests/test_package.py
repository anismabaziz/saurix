"""
Tests for what the package publishes and what version it claims.

The graph model is the part of Saurix a user imports, so its names and the
release they ship in are part of the contract rather than an implementation
detail. These tests hold that contract: the glossary's terms resolve, the old
ones do not, and the version reported at runtime is the one the packaging
metadata declares.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import saurix
import saurix.core
from saurix.core import models
from saurix.core.graph import GraphStore

REPO_ROOT = Path(__file__).resolve().parent.parent

# A package version written as a literal anywhere under the package.
# `saurix/__init__.py` reads the installed metadata, so a version spelled out is a
# second copy waiting to disagree with PyPI, which is how 0.1.0 and 0.2.0 drifted
# apart. The graph schema version is a different number and is left alone.
VERSION_LITERAL = re.compile(r"""__version__\s*[:=]\s*\(?\s*["'][^"']+["']""")


def _declared_version() -> str:
    """
    Read the version the packaging metadata declares, the one place it is written.
    """
    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    return str(pyproject["project"]["version"])


def _changelog_release() -> str:
    """
    Read the version the newest changelog entry describes.
    """
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"^## \[(\d+\.\d+\.\d+)\]", changelog, re.MULTILINE)
    assert match is not None, "CHANGELOG.md has no released version heading"
    return match.group(1)


class TestPublicSurface:
    """
    The graph model is exported under the glossary's terms.
    """

    def test_symbol_and_edge_are_exported(self) -> None:
        """
        `Symbol` and `Edge` are importable from the package and the core package.
        """
        assert saurix.core.Symbol is models.Symbol
        assert saurix.core.Edge is models.Edge
        assert set(saurix.core.__all__) >= {"Symbol", "Edge"}

    def test_the_old_name_is_not_exported(self) -> None:
        """
        Nothing re-exports the name 0.2.0 shipped under: the rename is a cut, not
        an alias, so the old vocabulary cannot creep back through an import.
        """
        assert not hasattr(saurix.core, "Node")
        assert not hasattr(models, "Node")
        assert "Node" not in saurix.core.__all__

    def test_the_store_speaks_the_same_vocabulary(self) -> None:
        """
        The store is renamed too, so a partial rename cannot pass for a whole one.
        """
        assert isinstance(GraphStore.symbols, property)
        assert callable(GraphStore.add_symbol)
        assert callable(GraphStore.get_symbols_by_name)
        for gone in ("nodes", "add_node", "get_nodes_by_name"):
            assert not hasattr(GraphStore, gone), f"GraphStore still has {gone}"


class TestVersion:
    """
    The version has one source.
    """

    def test_reported_version_is_the_declared_one(self) -> None:
        """
        `saurix.__version__` is the version the packaging metadata declares, so it
        cannot disagree with what was published.
        """
        assert saurix.__version__ == _declared_version()

    def test_the_release_has_a_changelog_entry(self) -> None:
        """
        The declared version is the one the changelog describes, so cutting a
        release without writing down what changed cannot pass.
        """
        assert _declared_version() == _changelog_release()


def test_no_module_writes_a_version_literal() -> None:
    """
    No module spells a version out, which is how the two copies drifted apart in
    the first place: one said 0.1.0 while the packaging metadata said 0.2.0.
    """
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in (REPO_ROOT / "saurix").rglob("*.py")
        if VERSION_LITERAL.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"these modules spell out a version: {offenders}"
