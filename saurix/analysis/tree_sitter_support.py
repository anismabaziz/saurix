from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Parser


class GrammarUnavailableError(RuntimeError):
    """
    Raised when the tree-sitter grammar for a language cannot be built.

    Each language has exactly one extraction path, so an unusable grammar is a
    broken install rather than a reason to extract something worse.
    """


def get_parser(language: str) -> Parser:
    """
    Build the tree-sitter parser for a language, or fail loudly.

    Grammars come from tree-sitter-language-pack, the maintained bundle. A
    grammar that will not load raises instead of returning nothing, so a
    broken install surfaces at startup rather than as quietly thinner graphs.
    """
    try:
        from tree_sitter_language_pack import get_parser as _get_parser
    except ImportError as e:
        raise GrammarUnavailableError(
            "tree-sitter-language-pack is not installed. "
            "Reinstall saurix to restore the grammars it needs."
        ) from e

    try:
        return _get_parser(language)
    except Exception as e:
        raise GrammarUnavailableError(
            f"No tree-sitter grammar could be loaded for {language!r}: {e}"
        ) from e


def walk(node) -> Iterator:
    stack = [node]
    while stack:
        cur = stack.pop()
        yield cur
        children = list(getattr(cur, "children", []))
        children.reverse()
        stack.extend(children)


def text_of(source: bytes, node) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def stripped_string(source: bytes, node) -> str:
    text = text_of(source, node).strip()
    if (
        text.startswith(("'", '"', "`"))
        and text.endswith(("'", '"', "`"))
        and len(text) >= 2
    ):
        return text[1:-1]
    return text


def find_first_desc(node, types: set[str]):
    for child in walk(node):
        if child.type in types:
            return child
    return None
