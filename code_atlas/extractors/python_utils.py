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


def call_confidence(raw_name: str, resolved: str, imports: dict[str, str]) -> str:
    head = raw_name.split(".", 1)[0]

    if ":" in resolved:
        return "high"

    if head in imports:
        return "high" if "." in raw_name else "medium"

    if resolved.startswith("python://") and raw_name == resolved.removeprefix("python://"):
        if head in _BUILTIN_CALLS:
            return "medium"
        return "low"

    if "." in raw_name:
        return "medium"

    return "medium"


_BUILTIN_CALLS = {
    "print",
    "len",
    "str",
    "int",
    "float",
    "dict",
    "list",
    "set",
    "tuple",
    "range",
    "open",
    "sum",
    "min",
    "max",
    "sorted",
    "enumerate",
    "zip",
    "map",
    "filter",
    "any",
    "all",
}


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
