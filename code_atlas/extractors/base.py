from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..graph import GraphStore


class Extractor(ABC):
    language: str

    @abstractmethod
    def extract(self, *, repo_root: Path, file_path: Path, graph: GraphStore) -> None:
        raise NotImplementedError
