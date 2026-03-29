from __future__ import annotations

import re
from pathlib import Path

from ..graph import GraphStore
from .common import add_calls_edge, add_contains_edge, add_import_edge, add_node
from .regex_lang import RegexLangExtractor
from .tree_sitter_support import find_first_desc, get_parser, stripped_string, text_of, walk


class GoExtractor:
    language = "go"

    def __init__(self) -> None:
        self._fallback = RegexLangExtractor(
            language="go",
            import_pattern=re.compile(r"import\s+(?:\(\s*)?(?:[\w\.]+\s+)?\"(?P<target>[^\"]+)\"", re.MULTILINE),
            function_pattern=re.compile(r"func\s+(?:\([^\)]*\)\s*)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(", re.MULTILINE),
            call_pattern=re.compile(r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\("),
        )
        self._parser = get_parser("go")

    def extract(self, *, repo_root: Path, file_path: Path, graph: GraphStore) -> None:
        if self._parser is None:
            self._fallback.extract(repo_root=repo_root, file_path=file_path, graph=graph)
            return

        rel = file_path.relative_to(repo_root).as_posix()
        source = file_path.read_bytes()
        root = self._parser.parse(source).root_node

        module_name = rel.rsplit(".", 1)[0].replace("/", ".")
        module_id = f"go://{module_name}"
        add_node(graph, node_id=module_id, node_type="module", language=self.language, name=module_name, file=rel, line=1)

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
        if node.type != "import_spec":
            return
        string_node = find_first_desc(node, {"interpreted_string_literal", "raw_string_literal"})
        if string_node is None:
            return
        target = stripped_string(source, string_node)
        if not target:
            return
        target_id = f"go://{target.replace('/', '.')}"
        add_node(graph, node_id=target_id, node_type="module", language=self.language, name=target)
        add_import_edge(graph, language=self.language, source=module_id, target=target_id, file=rel, line=node.start_point[0] + 1)

    def _extract_function(
        self,
        node,
        source: bytes,
        graph: GraphStore,
        module_id: str,
        rel: str,
        local_symbols: dict[str, str],
    ) -> None:
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
        add_node(graph, node_id=fn_id, node_type="function", language=self.language, name=name, file=rel, line=line)
        add_contains_edge(graph, language=self.language, source=module_id, target=fn_id, file=rel, line=line)
