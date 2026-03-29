from __future__ import annotations

import ast


def name_of(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = name_of(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return name_of(node.func)
    return None


def call_confidence(raw_name: str, resolved: str) -> str:
    if resolved.startswith("python://") and raw_name == resolved.removeprefix("python://"):
        return "low"
    if ":" in resolved:
        return "high"
    return "medium"


def resolve_name(
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
