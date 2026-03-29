from __future__ import annotations

import ast

from ..graph import GraphStore
from .common import add_calls_edge, add_contains_edge, add_node
from .python_utils import call_confidence, name_of, resolve_name


def add_class(
    *,
    graph: GraphStore,
    language: str,
    module_id: str,
    rel: str,
    class_node: ast.ClassDef,
    imports: dict[str, str],
    local_functions: set[str],
    class_methods: set[str],
) -> None:
    class_id = f"{module_id}:{class_node.name}"
    add_node(
        graph,
        node_id=class_id,
        node_type="class",
        language=language,
        name=class_node.name,
        file=rel,
        line=getattr(class_node, "lineno", None),
        metadata={"kind": "class"},
    )
    add_contains_edge(
        graph,
        language=language,
        source=module_id,
        target=class_id,
        file=rel,
        line=getattr(class_node, "lineno", None),
    )

    for child in class_node.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add_function(
                graph=graph,
                language=language,
                module_id=module_id,
                rel=rel,
                fn_node=child,
                imports=imports,
                local_functions=local_functions,
                class_name=class_node.name,
                class_methods=class_methods,
            )


def add_function(
    *,
    graph: GraphStore,
    language: str,
    module_id: str,
    rel: str,
    fn_node: ast.FunctionDef | ast.AsyncFunctionDef,
    imports: dict[str, str],
    local_functions: set[str],
    class_name: str | None,
    class_methods: set[str] | None,
) -> None:
    if class_name:
        fn_id = f"{module_id}:{class_name}.{fn_node.name}"
        fn_type = "method"
        parent_id = f"{module_id}:{class_name}"
    else:
        fn_id = f"{module_id}:{fn_node.name}"
        fn_type = "function"
        parent_id = module_id

    add_node(
        graph,
        node_id=fn_id,
        node_type=fn_type,
        language=language,
        name=fn_node.name,
        file=rel,
        line=getattr(fn_node, "lineno", None),
        metadata={"args": [arg.arg for arg in fn_node.args.args], "async": isinstance(fn_node, ast.AsyncFunctionDef)},
    )
    add_contains_edge(
        graph,
        language=language,
        source=parent_id,
        target=fn_id,
        file=rel,
        line=getattr(fn_node, "lineno", None),
    )

    for child in ast.walk(fn_node):
        if not isinstance(child, ast.Call):
            continue
        raw_name = name_of(child.func)
        if not raw_name:
            continue
        resolved = resolve_name(
            name=raw_name,
            module_id=module_id,
            imports=imports,
            local_functions=local_functions,
            class_name=class_name,
            class_methods=class_methods,
        )
        add_node(graph, node_id=resolved, node_type="symbol", language=language, name=raw_name)
        add_calls_edge(
            graph,
            language=language,
            source=fn_id,
            target=resolved,
            file=rel,
            line=getattr(child, "lineno", None),
            confidence=call_confidence(raw_name, resolved),
        )
