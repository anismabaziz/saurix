from __future__ import annotations

import re
from pathlib import Path

from ..graph import GraphStore
from .base import Extractor
from .common import add_calls_edge, add_contains_edge, add_import_edge, add_node


class RegexLangExtractor(Extractor):
    def __init__(
        self,
        *,
        language: str,
        import_pattern: re.Pattern[str],
        function_pattern: re.Pattern[str],
        call_pattern: re.Pattern[str],
    ) -> None:
        self.language = language
        self.import_pattern = import_pattern
        self.function_pattern = function_pattern
        self.call_pattern = call_pattern

    def extract(self, *, repo_root: Path, file_path: Path, graph: GraphStore) -> None:
        rel = file_path.relative_to(repo_root).as_posix()
        source = file_path.read_text(encoding="utf-8", errors="replace")
        module_name = rel.rsplit(".", 1)[0].replace("/", ".")
        module_id = f"{self.language}://{module_name}"
        add_node(graph, node_id=module_id, node_type="module", language=self.language, name=module_name, file=rel, line=1)

        for match in self.import_pattern.finditer(source):
            target = _first_group(match, "target", "target2").strip()
            if not target:
                continue
            target_id = f"{self.language}://{target.replace('/', '.')}"
            add_node(graph, node_id=target_id, node_type="module", language=self.language, name=target)
            add_import_edge(graph, language=self.language, source=module_id, target=target_id, file=rel, line=_line(source, match.start()))

        for match in self.function_pattern.finditer(source):
            name = _first_group(match, "name", "name2").strip()
            if not name:
                continue
            fn_id = f"{module_id}:{name}"
            add_node(graph, node_id=fn_id, node_type="function", language=self.language, name=name, file=rel, line=_line(source, match.start()))
            add_contains_edge(graph, language=self.language, source=module_id, target=fn_id, file=rel, line=_line(source, match.start()))

        module_symbols = {n.name: n.id for n in graph.nodes.values() if n.file == rel and n.type in {"function", "method"}}
        caller = next(iter(module_symbols.values()), module_id)
        for match in self.call_pattern.finditer(source):
            callee = (match.group("name") or "").strip()
            if not callee:
                continue
            target_id = module_symbols.get(callee, f"{self.language}://{callee}")
            add_node(graph, node_id=target_id, node_type="symbol", language=self.language, name=callee)
            add_calls_edge(
                graph,
                language=self.language,
                source=caller,
                target=target_id,
                file=rel,
                line=_line(source, match.start()),
                confidence="low" if target_id.startswith(f"{self.language}://") else "medium",
            )


def _line(source: str, char_idx: int) -> int:
    return source.count("\n", 0, char_idx) + 1


def _first_group(match: re.Match[str], *names: str) -> str:
    groups = match.groupdict()
    for name in names:
        value = groups.get(name)
        if value:
            return value
    return ""
