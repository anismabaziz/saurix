"""
Go extractor using Tree-sitter.
"""

from __future__ import annotations

from pathlib import Path

from ..core.graph import GraphStore
from ..core.models import Edge, Symbol
from .base import Extractor
from .tree_sitter_support import (
    find_first_desc,
    get_parser,
    stripped_string,
    text_of,
    walk,
)


class GoExtractor(Extractor):
    """
    Language-specific extractor for Go, built on the Go tree-sitter grammar.
    """

    language = "go"

    def __init__(self) -> None:
        self._parser = get_parser("go")

    def extract(self, *, repo_root: Path, file_path: Path, graph: GraphStore) -> None:
        """
        Extract module/import/function/call relationships from Go files.
        """
        rel = file_path.relative_to(repo_root).as_posix()
        source = file_path.read_bytes()
        root = self._parser.parse(source).root_node

        module_name = rel.rsplit(".", 1)[0].replace("/", ".")
        module_id = f"go://{module_name}"
        graph.add_symbol(
            Symbol(
                id=module_id,
                type="module",
                language=self.language,
                name=module_name,
                file=rel,
                line=1,
            )
        )

        local_symbols: dict[str, str] = {}
        for node in walk(root):
            self._extract_import(node, source, graph, module_id, rel)
            self._extract_function(node, source, graph, module_id, rel, local_symbols)

        caller_id = next(iter(local_symbols.values()), module_id)
        for node in walk(root):
            if node.type != "call_expression":
                continue
            ident = find_first_desc(node, {"identifier", "field_identifier"})
            if ident is None:
                continue
            name = text_of(source, ident).strip()
            if not name:
                continue
            target = local_symbols.get(name, f"go://{name}")
            graph.add_symbol(
                Symbol(id=target, type="symbol", language=self.language, name=name)
            )
            graph.add_edge(
                Edge(
                    type="CALLS",
                    source=caller_id,
                    target=target,
                    language=self.language,
                    confidence="medium" if target in local_symbols.values() else "low",
                    file=rel,
                    line=node.start_point[0] + 1,
                )
            )

    def _extract_import(
        self, node, source: bytes, graph: GraphStore, module_id: str, rel: str
    ) -> None:
        """
        Extract one import edge from a Go import spec node.
        """
        if node.type != "import_spec":
            return
        string_node = find_first_desc(
            node, {"interpreted_string_literal", "raw_string_literal"}
        )
        if string_node is None:
            return
        target = stripped_string(source, string_node)
        if not target:
            return
        target_id = f"go://{target.replace('/', '.')}"
        graph.add_symbol(
            Symbol(id=target_id, type="module", language=self.language, name=target)
        )
        graph.add_edge(
            Edge(
                type="IMPORTS",
                source=module_id,
                target=target_id,
                language=self.language,
                confidence="high",
                file=rel,
                line=node.start_point[0] + 1,
            )
        )

    def _extract_function(
        self,
        node,
        source: bytes,
        graph: GraphStore,
        module_id: str,
        rel: str,
        local_symbols: dict[str, str],
    ) -> None:
        """
        Extract function declaration and add module containment edge.
        """
        if node.type != "function_declaration":
            return
        ident = find_first_desc(node, {"identifier"})
        if ident is None:
            return
        name = text_of(source, ident).strip()
        if not name:
            return
        fn_id = f"{module_id}:{name}"
        local_symbols[name] = fn_id
        line = node.start_point[0] + 1
        graph.add_symbol(
            Symbol(
                id=fn_id,
                type="function",
                language=self.language,
                name=name,
                file=rel,
                line=line,
            )
        )
        graph.add_edge(
            Edge(
                type="CONTAINS",
                source=module_id,
                target=fn_id,
                language=self.language,
                confidence="high",
                file=rel,
                line=line,
            )
        )
