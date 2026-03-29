from __future__ import annotations

"""TypeScript extractor using Tree-sitter with regex fallback."""

import re
from pathlib import Path

from ..graph import GraphStore
from .common import add_calls_edge, add_contains_edge, add_import_edge, add_node
from .regex_lang import RegexLangExtractor
from .tree_sitter_support import find_first_desc, get_parser, stripped_string, text_of, walk


class TypeScriptExtractor:
    language = "typescript"

    def __init__(self) -> None:
        self._fallback = RegexLangExtractor(
            language="typescript",
            import_pattern=re.compile(
                r"(?:import\s+.+?\s+from\s+['\"](?P<target>[^'\"]+)['\"]|import\s+['\"](?P<target2>[^'\"]+)['\"])",
                re.MULTILINE,
            ),
            function_pattern=re.compile(
                r"(?:function\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(|(?:const|let|var)\s+(?P<name2>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*\([^\)]*\)\s*=>)",
                re.MULTILINE,
            ),
            call_pattern=re.compile(r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\("),
        )
        self._parser = get_parser("typescript")

    def extract(self, *, repo_root: Path, file_path: Path, graph: GraphStore) -> None:
        """Extract module/import/function/call relationships from TS files."""
        if self._parser is None:
            self._fallback.extract(repo_root=repo_root, file_path=file_path, graph=graph)
            return

        rel = file_path.relative_to(repo_root).as_posix()
        source = file_path.read_bytes()
        tree = self._parser.parse(source)
        root = tree.root_node

        module_name = rel.rsplit(".", 1)[0].replace("/", ".")
        module_id = f"typescript://{module_name}"
        add_node(graph, node_id=module_id, node_type="module", language=self.language, name=module_name, file=rel, line=1)

        local_symbols: dict[str, str] = {}
        for node in walk(root):
            self._extract_import(node, source, graph, module_id, rel)
            self._extract_function_like(node, source, graph, module_id, rel, local_symbols)

        caller_id = next(iter(local_symbols.values()), module_id)
        for node in walk(root):
            if node.type != "call_expression":
                continue
            callee = find_first_desc(node, {"identifier", "property_identifier"})
            if callee is None:
                continue
            name = text_of(source, callee).strip()
            if not name:
                continue
            target = local_symbols.get(name, f"typescript://{name}")
            add_node(graph, node_id=target, node_type="symbol", language=self.language, name=name)
            add_calls_edge(
                graph,
                language=self.language,
                source=caller_id,
                target=target,
                file=rel,
                line=node.start_point[0] + 1,
                confidence="medium" if target in local_symbols.values() else "low",
            )

    def _extract_import(self, node, source: bytes, graph: GraphStore, module_id: str, rel: str) -> None:
        """Extract one import edge from a TS import statement node."""
        if node.type != "import_statement":
            return
        s = find_first_desc(node, {"string"})
        if s is None:
            return
        target = stripped_string(source, s)
        if not target:
            return
        target_id = f"typescript://{target.replace('/', '.')}"
        add_node(graph, node_id=target_id, node_type="module", language=self.language, name=target)
        add_import_edge(graph, language=self.language, source=module_id, target=target_id, file=rel, line=node.start_point[0] + 1)

    def _extract_function_like(self, node, source: bytes, graph: GraphStore, module_id: str, rel: str, local_symbols: dict[str, str]) -> None:
        """Extract function declarations and arrow-function variable bindings."""
        if node.type == "function_declaration":
            ident = find_first_desc(node, {"identifier"})
            if ident is None:
                return
            name = text_of(source, ident).strip()
            self._register_symbol(graph, module_id, rel, local_symbols, name, node.start_point[0] + 1)
            return

        if node.type in {"lexical_declaration", "variable_declaration"}:
            for child in getattr(node, "children", []):
                if child.type != "variable_declarator":
                    continue
                ident = find_first_desc(child, {"identifier"})
                arrow = find_first_desc(child, {"arrow_function"})
                if ident is None or arrow is None:
                    continue
                name = text_of(source, ident).strip()
                self._register_symbol(graph, module_id, rel, local_symbols, name, child.start_point[0] + 1)

    def _register_symbol(
        self,
        graph: GraphStore,
        module_id: str,
        rel: str,
        local_symbols: dict[str, str],
        name: str,
        line: int,
    ) -> None:
        """Create function node and containment edge for discovered symbol."""
        if not name:
            return
        fn_id = f"{module_id}:{name}"
        local_symbols[name] = fn_id
        add_node(graph, node_id=fn_id, node_type="function", language=self.language, name=name, file=rel, line=line)
        add_contains_edge(graph, language=self.language, source=module_id, target=fn_id, file=rel, line=line)
