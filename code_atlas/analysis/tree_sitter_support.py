from __future__ import annotations

from typing import Iterator
import warnings


def get_parser(language: str):
    try:
        from tree_sitter_languages import get_parser as _get_parser
    except Exception:
        return None

    try:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                category=FutureWarning,
                message=r"Language\(path, name\) is deprecated.*",
            )
            return _get_parser(language)
    except Exception:
        return None


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
    if text.startswith(("'", '"', "`")) and text.endswith(("'", '"', "`")) and len(text) >= 2:
        return text[1:-1]
    return text


def find_first_desc(node, types: set[str]):
    for child in walk(node):
        if child.type in types:
            return child
    return None
