from __future__ import annotations

"""TypeScript extractor using Tree-sitter with regex fallback."""

import re
from pathlib import Path
from typing import Any

from ..graph import GraphStore
from ..models import Edge
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

        # Track all local symbols (functions, classes, methods)
        local_symbols: dict[str, str] = {}
        # Track class members for method resolution
        class_members: dict[str, dict[str, str]] = {}
        # Track imports for resolution
        imports: dict[str, str] = {}

        # First pass: extract imports
        for node in walk(root):
            self._extract_import(node, source, graph, module_id, rel, imports)

        # Second pass: extract declarations
        for node in walk(root):
            self._extract_function_like(node, source, graph, module_id, rel, local_symbols)
            self._extract_class(node, source, graph, module_id, rel, local_symbols, class_members)
            self._extract_interface(node, source, graph, module_id, rel, local_symbols)

        # Third pass: extract calls
        for node in walk(root):
            self._extract_calls(node, source, graph, module_id, rel, local_symbols, class_members, imports)

    def _extract_import(self, node, source: bytes, graph: GraphStore, module_id: str, rel: str, imports: dict[str, str]) -> None:
        """Extract one import edge from a TS import statement node."""
        if node.type != "import_statement":
            return

        # Handle: import { foo, bar } from "module"
        import_clause = find_first_desc(node, {"import_clause"})
        if import_clause:
            # Named imports
            named_imports = find_first_desc(import_clause, {"named_imports"})
            if named_imports:
                for child in getattr(named_imports, "children", []):
                    if child.type == "import_specifier":
                        ident = find_first_desc(child, {"identifier", "type_identifier"})
                        if ident:
                            name = text_of(source, ident).strip()
                            # Check for alias: import { foo as bar }
                            alias = None
                            for c in getattr(child, "children", []):
                                if c.type == "identifier" and c != ident:
                                    alias = text_of(source, c).strip()
                                    break
                            local_name = alias if alias else name

                            string_node = find_first_desc(node, {"string"})
                            if string_node:
                                target = stripped_string(source, string_node)
                                if target:
                                    target_id = f"typescript://{target.replace('/', '.')}"
                                    add_node(graph, node_id=target_id, node_type="module", language=self.language, name=target)
                                    add_import_edge(graph, language=self.language, source=module_id, target=target_id, file=rel, line=node.start_point[0] + 1)
                                    imports[local_name] = target_id
            else:
                # Default import: import foo from "module"
                ident = find_first_desc(import_clause, {"identifier", "type_identifier"})
                if ident:
                    name = text_of(source, ident).strip()
                    string_node = find_first_desc(node, {"string"})
                    if string_node:
                        target = stripped_string(source, string_node)
                        if target:
                            target_id = f"typescript://{target.replace('/', '.')}"
                            add_node(graph, node_id=target_id, node_type="module", language=self.language, name=target)
                            add_import_edge(graph, language=self.language, source=module_id, target=target_id, file=rel, line=node.start_point[0] + 1)
                            imports[name] = target_id
            return

        # Handle: import * as foo from "module"
        namespace_import = find_first_desc(node, {"namespace_import"})
        if namespace_import:
            ident = find_first_desc(namespace_import, {"identifier"})
            if ident:
                name = text_of(source, ident).strip()
                string_node = find_first_desc(node, {"string"})
                if string_node:
                    target = stripped_string(source, string_node)
                    if target:
                        target_id = f"typescript://{target.replace('/', '.')}"
                        add_node(graph, node_id=target_id, node_type="module", language=self.language, name=target)
                        add_import_edge(graph, language=self.language, source=module_id, target=target_id, file=rel, line=node.start_point[0] + 1)
                        imports[name] = target_id
            return

        # Handle: import "module" (side effect)
        s = find_first_desc(node, {"string"})
        if s:
            target = stripped_string(source, s)
            if target:
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
                function = find_first_desc(child, {"function"})
                if ident and (arrow or function):
                    name = text_of(source, ident).strip()
                    self._register_symbol(graph, module_id, rel, local_symbols, name, child.start_point[0] + 1)

    def _extract_class(
        self,
        node: Any,
        source: bytes,
        graph: GraphStore,
        module_id: str,
        rel: str,
        local_symbols: dict[str, str],
        class_members: dict[str, dict[str, str]],
    ) -> None:
        """Extract class declarations and their methods."""
        if node.type not in {"class_declaration", "class"}:
            return

        ident = find_first_desc(node, {"type_identifier", "identifier"})
        if ident is None:
            return

        class_name = text_of(source, ident).strip()
        if not class_name:
            return

        # Register class
        class_id = f"{module_id}:{class_name}"
        local_symbols[class_name] = class_id
        class_members[class_name] = {}

        add_node(graph, node_id=class_id, node_type="class", language=self.language, name=class_name, file=rel, line=node.start_point[0] + 1)
        add_contains_edge(graph, language=self.language, source=module_id, target=class_id, file=rel, line=node.start_point[0] + 1)

        # Extract inheritance
        for child in getattr(node, "children", []):
            if child.type == "class_heritage":
                parent = find_first_desc(child, {"type_identifier", "identifier"})
                if parent:
                    parent_name = text_of(source, parent).strip()
                    parent_id = f"typescript://{parent_name}"  # Best effort resolution
                    add_node(graph, node_id=parent_id, node_type="class", language=self.language, name=parent_name)
                    graph.add_edge(Edge(type="INHERITS", source=class_id, target=parent_id, language=self.language, confidence="medium", file=rel, line=child.start_point[0] + 1))

        # Extract class body members
        class_body = find_first_desc(node, {"class_body"})
        if class_body:
            for member in getattr(class_body, "children", []):
                if member.type in {"method_definition", "public_field_definition"}:
                    member_ident = find_first_desc(member, {"property_identifier", "identifier"})
                    if member_ident:
                        member_name = text_of(source, member_ident).strip()
                        member_type = "method" if member.type == "method_definition" else "property"
                        member_id = f"{class_id}.{member_name}"
                        class_members[class_name][member_name] = member_id
                        local_symbols[member_name] = member_id  # Also add to local symbols for simple resolution

                        add_node(graph, node_id=member_id, node_type=member_type, language=self.language, name=member_name, file=rel, line=member.start_point[0] + 1)
                        add_contains_edge(graph, language=self.language, source=class_id, target=member_id, file=rel, line=member.start_point[0] + 1)

    def _extract_interface(self, node, source: bytes, graph: GraphStore, module_id: str, rel: str, local_symbols: dict[str, str]) -> None:
        """Extract interface declarations."""
        if node.type != "interface_declaration":
            return

        ident = find_first_desc(node, {"type_identifier"})
        if ident is None:
            return

        name = text_of(source, ident).strip()
        if not name:
            return

        interface_id = f"{module_id}:{name}"
        local_symbols[name] = interface_id

        add_node(graph, node_id=interface_id, node_type="interface", language=self.language, name=name, file=rel, line=node.start_point[0] + 1)
        add_contains_edge(graph, language=self.language, source=module_id, target=interface_id, file=rel, line=node.start_point[0] + 1)

    def _extract_calls(
        self,
        node: Any,
        source: bytes,
        graph: GraphStore,
        module_id: str,
        rel: str,
        local_symbols: dict[str, str],
        class_members: dict[str, dict[str, str]],
        imports: dict[str, str],
    ) -> None:
        """Extract call expressions with improved resolution."""
        if node.type != "call_expression":
            return

        callee = node.children[0] if node.children else None
        if callee is None:
            return

        target_id: str | None = None
        confidence = "low"

        # Handle different callee types
        if callee.type == "identifier":
            # Simple call: foo()
            name = text_of(source, callee).strip()
            if name in local_symbols:
                target_id = local_symbols[name]
                confidence = "high"
            elif name in imports:
                target_id = f"{imports[name]}:{name}"
                confidence = "medium"
            else:
                target_id = f"typescript://{name}"

        elif callee.type == "member_expression":
            # Method call: obj.method() or Class.method()
            obj_node = find_first_desc(callee, {"identifier", "this"})
            method_node = find_first_desc(callee, {"property_identifier"})

            if method_node:
                method_name = text_of(source, method_node).strip()

                if obj_node:
                    obj_name = text_of(source, obj_node).strip()

                    if obj_name == "this" and class_members:
                        # this.method() - try to resolve within current class context
                        for class_name, members in class_members.items():
                            if method_name in members:
                                target_id = members[method_name]
                                confidence = "high"
                                break

                    if target_id is None and obj_name in local_symbols:
                        # obj.method() where obj is a known class
                        obj_id = local_symbols[obj_name]
                        if obj_id in [f"{module_id}:{cn}" for cn in class_members]:
                            class_name = obj_id.split(":")[-1]
                            if class_name in class_members and method_name in class_members[class_name]:
                                target_id = class_members[class_name][method_name]
                                confidence = "high"

                if target_id is None:
                    # Fall back to best effort
                    target_id = f"typescript://{method_name}"

        elif callee.type == "call_expression":
            # Chained call: foo()() - skip for now
            return

        if target_id:
            # Find the enclosing function/class as the caller
            caller_id = self._find_enclosing_scope(node, source, module_id, local_symbols, class_members)

            add_node(graph, node_id=target_id, node_type="symbol", language=self.language, name=target_id.split(":")[-1].split(".")[-1])
            add_calls_edge(
                graph,
                language=self.language,
                source=caller_id,
                target=target_id,
                file=rel,
                line=node.start_point[0] + 1,
                confidence=confidence,
            )

    def _find_enclosing_scope(
        self,
        node: Any,
        source: bytes,
        module_id: str,
        local_symbols: dict[str, str],
        class_members: dict[str, dict[str, str]],
    ) -> str:
        """Find the enclosing function or class for a node."""
        current = node
        while current:
            if current.type in {"function_declaration", "method_definition", "arrow_function"}:
                ident = find_first_desc(current, {"identifier", "property_identifier"})
                if ident:
                    name = text_of(source, ident).strip()
                    if name in local_symbols:
                        return local_symbols[name]
            elif current.type in {"class_declaration", "class"}:
                ident = find_first_desc(current, {"type_identifier", "identifier"})
                if ident:
                    name = text_of(source, ident).strip()
                    if name in local_symbols:
                        return local_symbols[name]
            current = getattr(current, "parent", None)
        return module_id

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
