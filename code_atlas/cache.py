from __future__ import annotations

"""Incremental indexing cache helpers for file fingerprints and contributions."""

import hashlib
import json
from pathlib import Path

from .models import Edge, Node


CACHE_VERSION = 1
DEFAULT_CACHE_PATH = Path("tmp") / "code-atlas.cache.json"
EXTRACTOR_VERSIONS = {
    "python": "2",
    "typescript": "2",
    "go": "2",
    "java": "1",
}


def file_hash(path: Path) -> str:
    """Compute content hash used for per-file incremental invalidation."""
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def load_cache(path: Path) -> dict[str, object]:
    """Load cache safely; return empty cache on mismatch/corruption."""
    if not path.exists():
        return _empty_cache()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _empty_cache()

    if payload.get("version") != CACHE_VERSION:
        return _empty_cache()
    if payload.get("extractor_versions") != EXTRACTOR_VERSIONS:
        return _empty_cache()
    if not isinstance(payload.get("files"), dict):
        return _empty_cache()
    return payload


def save_cache(path: Path, files: dict[str, dict[str, object]]) -> None:
    """Persist normalized cache payload to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CACHE_VERSION,
        "extractor_versions": EXTRACTOR_VERSIONS,
        "files": files,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def serialize_contribution(nodes: list[Node], edges: list[Edge], *, lang: str, fingerprint: str, parser_mode: str) -> dict[str, object]:
    """Serialize one file contribution for cache reuse."""
    return {
        "lang": lang,
        "hash": fingerprint,
        "parser_mode": parser_mode,
        "nodes": [n.__dict__ for n in nodes],
        "edges": [e.__dict__ for e in edges],
    }


def deserialize_contribution(row: dict[str, object]) -> tuple[list[Node], list[Edge]]:
    """Restore Node/Edge dataclasses from cached contribution row."""
    nodes = [Node(**n) for n in row.get("nodes", []) if isinstance(n, dict)]
    edges = [Edge(**e) for e in row.get("edges", []) if isinstance(e, dict)]
    return nodes, edges


def _empty_cache() -> dict[str, object]:
    return {
        "version": CACHE_VERSION,
        "extractor_versions": EXTRACTOR_VERSIONS,
        "files": {},
    }
