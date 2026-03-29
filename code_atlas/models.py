from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Node:
    id: str
    type: str
    language: str
    name: str
    file: str | None = None
    line: int | None = None
    column: int | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class Edge:
    type: str
    source: str
    target: str
    language: str
    confidence: str = "medium"
    file: str | None = None
    line: int | None = None
    column: int | None = None
    metadata: dict[str, Any] | None = None
