from __future__ import annotations

import ast
from pathlib import Path

from .base import Extractor
from ..graph import GraphStore
from ..models import Edge, Node


class PythonExtractor(Extractor):
    language = "python"

    def extract(self, *, repo_root: Path, file_path: Path, graph: GraphStore) -> None:
        rel = file_path.relative_to(repo_root).as_posix()
        source = file_path.read_text(encoding="utf-8", errors="replace")

        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            graph.add_node(
                Node(
                    id=f"python://{rel}",
                    type="file",
                    language=self.language,
                    name=file_path.name,
                    file=rel,
                    metadata={
                        "parse_error": str(exc),
                    },
                )
            )
            return

        module_name = rel[:-3].replace("/", ".") if rel.endswith(".py") else rel
        module_id = f"python://{module_name}"

        graph.add_node(
            Node(
                id=module_id,
                type="module",
                language=self.language,
                name=module_name,
                file=rel,
                line=1,
            )
        )

        imports: dict[str, str] = {}
        local_functions: set[str] = set()
        class_methods: dict[str, set[str]] = {}

        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = alias.name
                    alias_name = alias.asname or alias.name.split(".")[0]
                    imports[alias_name] = target

                    target_id = f"python://{target}"
                    graph.add_node(
                        Node(
                            id=target_id,
                            type="module",
                            language=self.language,
                            name=target,
                        )
                    )
                    graph.add_edge(
                        Edge(
                            type="IMPORTS",
                            source=module_id,
                            target=target_id,
                            language=self.language,
                            confidence="high",
                            file=rel,
                            line=getattr(node, "lineno", None),
                        )
                    )

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imported_name = alias.name
                    alias_name = alias.asname or imported_name

                    resolved = f"{module}.{imported_name}" if module else imported_name
                    imports[alias_name] = resolved

                    target_id = f"python://{resolved}"
                    graph.add_node(
                        Node(
                            id=target_id,
                            type="symbol",
                            language=self.language,
                            name=resolved,
                        )
                    )
                    graph.add_edge(
                        Edge(
                            type="IMPORTS",
                            source=module_id,
                            target=target_id,
                            language=self.language,
                            confidence="high",
                            file=rel,
                            line=getattr(node, "lineno", None),
                        )
                    )

            elif isinstance(node, ast.FunctionDef):
                local_functions.add(node.name)

            elif isinstance(node, ast.ClassDef):
                methods = {
                    item.name
                    for item in node.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                class_methods[node.name] = methods

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._add_function(
                    graph=graph,
                    module_id=module_id,
                    rel=rel,
                    fn_node=node,
                    imports=imports,
                    local_functions=local_functions,
                    class_name=None,
                    class_methods=None,
                )
            elif isinstance(node, ast.ClassDef):
                self._add_class(
                    graph=graph,
                    module_id=module_id,
                    rel=rel,
                    class_node=node,
                    imports=imports,
                    local_functions=local_functions,
                    class_methods=class_methods.get(node.name, set()),
                )

    def _add_class(
        self,
        *,
        graph: GraphStore,
        module_id: str,
        rel: str,
        class_node: ast.ClassDef,
        imports: dict[str, str],
        local_functions: set[str],
        class_methods: set[str],
    ) -> None:
        class_id = f"{module_id}:{class_node.name}"
        graph.add_node(
            Node(
                id=class_id,
                type="class",
                language=self.language,
                name=class_node.name,
                file=rel,
                line=getattr(class_node, "lineno", None),
                metadata={"kind": "class"},
            )
        )
        graph.add_edge(
            Edge(
                type="CONTAINS",
                source=module_id,
                target=class_id,
                language=self.language,
                confidence="high",
                file=rel,
                line=getattr(class_node, "lineno", None),
            )
        )

        for base in class_node.bases:
            base_name = self._name_of(base)
            if base_name is None:
                continue
            resolved = self._resolve_name(
                name=base_name,
                module_id=module_id,
                imports=imports,
                local_functions=local_functions,
                class_name=class_node.name,
                class_methods=class_methods,
            )
            graph.add_node(
                Node(
                    id=resolved,
                    type="class",
                    language=self.language,
                    name=base_name,
                )
            )
            graph.add_edge(
                Edge(
                    type="INHERITS",
                    source=class_id,
                    target=resolved,
                    language=self.language,
                    confidence="medium",
                    file=rel,
                    line=getattr(base, "lineno", None),
                )
            )

        for child in class_node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._add_function(
                    graph=graph,
                    module_id=module_id,
                    rel=rel,
                    fn_node=child,
                    imports=imports,
                    local_functions=local_functions,
                    class_name=class_node.name,
                    class_methods=class_methods,
                )

    def _add_function(
        self,
        *,
        graph: GraphStore,
        module_id: str,
        rel: str,
        fn_node: ast.FunctionDef | ast.AsyncFunctionDef,
        imports: dict[str, str],
        local_functions: set[str],
        class_name: str | None,
        class_methods: set[str] | None,
    ) -> None:
        if class_name:
            function_id = f"{module_id}:{class_name}.{fn_node.name}"
            fn_type = "method"
            parent_id = f"{module_id}:{class_name}"
        else:
            function_id = f"{module_id}:{fn_node.name}"
            fn_type = "function"
            parent_id = module_id

        graph.add_node(
            Node(
                id=function_id,
                type=fn_type,
                language=self.language,
                name=fn_node.name,
                file=rel,
                line=getattr(fn_node, "lineno", None),
                metadata={
                    "args": [arg.arg for arg in fn_node.args.args],
                    "async": isinstance(fn_node, ast.AsyncFunctionDef),
                },
            )
        )
        graph.add_edge(
            Edge(
                type="CONTAINS",
                source=parent_id,
                target=function_id,
                language=self.language,
                confidence="high",
                file=rel,
                line=getattr(fn_node, "lineno", None),
            )
        )

        for child in ast.walk(fn_node):
            if isinstance(child, ast.Call):
                raw_name = self._name_of(child.func)
                if not raw_name:
                    continue
                resolved = self._resolve_name(
                    name=raw_name,
                    module_id=module_id,
                    imports=imports,
                    local_functions=local_functions,
                    class_name=class_name,
                    class_methods=class_methods,
                )
                graph.add_node(
                    Node(
                        id=resolved,
                        type="symbol",
                        language=self.language,
                        name=raw_name,
                    )
                )
                graph.add_edge(
                    Edge(
                        type="CALLS",
                        source=function_id,
                        target=resolved,
                        language=self.language,
                        confidence=self._call_confidence(raw_name, resolved),
                        file=rel,
                        line=getattr(child, "lineno", None),
                    )
                )

    def _call_confidence(self, raw_name: str, resolved: str) -> str:
        if resolved.startswith("python://") and raw_name == resolved.removeprefix("python://"):
            return "low"
        if ":" in resolved:
            return "high"
        return "medium"

    def _resolve_name(
        self,
        *,
        name: str,
        module_id: str,
        imports: dict[str, str],
        local_functions: set[str],
        class_name: str | None,
        class_methods: set[str] | None,
    ) -> str:
        if class_name and class_methods and name.startswith("self."):
            maybe = name.split(".", 1)[1]
            if maybe in class_methods:
                return f"{module_id}:{class_name}.{maybe}"

        if name in local_functions:
            return f"{module_id}:{name}"

        head = name.split(".", 1)[0]
        if head in imports:
            imported = imports[head]
            if "." in name:
                suffix = name.split(".", 1)[1]
                return f"python://{imported}.{suffix}"
            return f"python://{imported}"

        return f"python://{name}"

    def _name_of(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = self._name_of(node.value)
            if parent:
                return f"{parent}.{node.attr}"
            return node.attr
        if isinstance(node, ast.Call):
            return self._name_of(node.func)
        return None
