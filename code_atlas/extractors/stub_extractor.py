from __future__ import annotations

from pathlib import Path

from .base import Extractor
from ..graph import GraphStore
from ..models import Node


class StubExtractor(Extractor):
    def __init__(self, language: str) -> None:
        self.language = language

    def extract(self, *, repo_root: Path, file_path: Path, graph: GraphStore) -> None:
        rel = file_path.relative_to(repo_root).as_posix()
        file_id = f"{self.language}://{rel}"
        graph.add_node(
            Node(
                id=file_id,
                type="file",
                language=self.language,
                name=file_path.name,
                file=rel,
                metadata={"status": "stub_extractor"},
            )
        )
