from __future__ import annotations

import ast
from pathlib import Path

from .base import Extractor
from .common import add_import_edge, add_node
from .python_builder import add_class, add_function
from .python_utils import name_of, resolve_name
from ..graph import GraphStore
from ..models import Edge


class PythonExtractor(Extractor):
    language = "python"

    def extract(self, *, repo_root: Path, file_path: Path, graph: GraphStore) -> None:
        rel = file_path.relative_to(repo_root).as_posix()
        source = file_path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            add_node(
                graph,
                node_id=f"python://{rel}",
                node_type="file",
                language=self.language,
                name=file_path.name,
                file=rel,
                metadata={"parse_error": str(exc)},
            )
            return

        module_name = rel[:-3].replace("/", ".") if rel.endswith(".py") else rel
        module_id = f"python://{module_name}"
        add_node(graph, node_id=module_id, node_type="module", language=self.language, name=module_name, file=rel, line=1)

        imports, local_functions, class_methods = self._collect_context(tree, graph, module_id, rel)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                add_function(
                    graph=graph,
                    language=self.language,
                    module_id=module_id,
                    rel=rel,
                    fn_node=node,
                    imports=imports,
                    local_functions=local_functions,
                    class_name=None,
                    class_methods=None,
                )
            elif isinstance(node, ast.ClassDef):
                methods = class_methods.get(node.name, set())
                add_class(
                    graph=graph,
                    language=self.language,
                    module_id=module_id,
                    rel=rel,
                    class_node=node,
                    imports=imports,
                    local_functions=local_functions,
                    class_methods=methods,
                )
                self._add_inherits(graph, module_id, rel, node, imports, local_functions, methods)

    def _collect_context(
        self,
        tree: ast.Module,
        graph: GraphStore,
        module_id: str,
        rel: str,
    ) -> tuple[dict[str, str], set[str], dict[str, set[str]]]:
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
                    add_node(graph, node_id=target_id, node_type="module", language=self.language, name=target)
                    add_import_edge(graph, language=self.language, source=module_id, target=target_id, file=rel, line=getattr(node, "lineno", None))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imported_name = alias.name
                    alias_name = alias.asname or imported_name
                    resolved = f"{module}.{imported_name}" if module else imported_name
                    imports[alias_name] = resolved
                    target_id = f"python://{resolved}"
                    add_node(graph, node_id=target_id, node_type="symbol", language=self.language, name=resolved)
                    add_import_edge(graph, language=self.language, source=module_id, target=target_id, file=rel, line=getattr(node, "lineno", None))
            elif isinstance(node, ast.FunctionDef):
                local_functions.add(node.name)
            elif isinstance(node, ast.ClassDef):
                methods = {item.name for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))}
                class_methods[node.name] = methods

        return imports, local_functions, class_methods

    def _add_inherits(
        self,
        graph: GraphStore,
        module_id: str,
        rel: str,
        class_node: ast.ClassDef,
        imports: dict[str, str],
        local_functions: set[str],
        class_methods: set[str],
    ) -> None:
        class_id = f"{module_id}:{class_node.name}"
        for base in class_node.bases:
            base_name = name_of(base)
            if base_name is None:
                continue
            resolved = resolve_name(
                name=base_name,
                module_id=module_id,
                imports=imports,
                local_functions=local_functions,
                class_name=class_node.name,
                class_methods=class_methods,
            )
            add_node(graph, node_id=resolved, node_type="class", language=self.language, name=base_name)
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
