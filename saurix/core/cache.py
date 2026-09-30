"""Incremental indexing cache.

Remembers what each indexed file contributed to the graph, so a second run
over an unchanged tree skips the extraction work. One repository owns exactly
one cache file; deleting it resets the next run to a full extraction.

A cache entry is trusted only when the file's modification time and content
hash both match. The whole file is discarded when it comes from somewhere
else: another repository, another machine, or another extraction version.
"""

from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .graph import SCHEMA_VERSION
from .models import Edge, Symbol

# Bumped when the on-disk shape below changes. A reader that does not know
# the shape discards the file rather than trusting half of it.
CACHE_VERSION = 2

# The cache lives inside the indexed repository, next to nothing else, so
# removing one file resets indexing. `tmp/` is gitignored and excluded from
# the scan, so the cache never indexes itself.
DEFAULT_CACHE_PATH = Path("tmp") / "saurix.cache.json"


def file_hash(path: Path) -> str:
    """
    Return the SHA-256 hex digest of a file's bytes.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _host_id() -> str:
    """
    Return the machine this process runs on, for cache fingerprinting.
    """
    return platform.node()


def _saurix_version() -> str:
    """
    Return the running Saurix version, for cache fingerprinting.
    """
    from .. import __version__

    return __version__


def _fingerprint(repo_root: Path) -> dict[str, object]:
    """
    Return the identity a cache file must carry to be trusted here.
    """
    return {
        "repo_root": str(repo_root.resolve()),
        "host_id": _host_id(),
        "saurix_version": _saurix_version(),
        "schema_version": SCHEMA_VERSION,
    }


def load_cache(path: Path, repo_root: Path) -> dict[str, dict[str, Any]]:
    """
    Return the cached per-file rows, or an empty mapping when untrusted.

    Anything unexpected discards the cache: a missing or unreadable file,
    invalid JSON, a version the reader does not know, or a fingerprint from
    another repository, another machine, or another extraction version.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    if payload.get("version") != CACHE_VERSION:
        return {}
    if not isinstance(payload.get("files"), dict):
        return {}
    expected = _fingerprint(repo_root)
    for key, value in expected.items():
        if payload.get(key) != value:
            return {}
    files = payload["files"]
    return {
        rel: row
        for rel, row in files.items()
        if isinstance(rel, str) and isinstance(row, dict)
    }


def save_cache(path: Path, files: dict[str, dict[str, Any]], repo_root: Path) -> None:
    """
    Persist per-file rows to the single cache file, stamped for this repo.
    """
    payload: dict[str, Any] = {
        "version": CACHE_VERSION,
        **_fingerprint(repo_root),
        "files": files,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def serialize_contribution(
    symbols: list[Symbol],
    edges: list[Edge],
    *,
    lang: str,
    content_hash: str,
    mtime_ns: int,
) -> dict[str, Any]:
    """
    Pack one file's extracted symbols and edges into a cache row.
    """
    return {
        "lang": lang,
        "hash": content_hash,
        "mtime_ns": mtime_ns,
        "symbols": [asdict(symbol) for symbol in symbols],
        "edges": [asdict(edge) for edge in edges],
    }


def deserialize_contribution(
    row: dict[str, Any],
) -> tuple[list[Symbol], list[Edge]]:
    """
    Restore a file's symbols and edges from a cache row.
    """
    symbols = [
        Symbol(**item) for item in row.get("symbols", []) if isinstance(item, dict)
    ]
    edges = [Edge(**item) for item in row.get("edges", []) if isinstance(item, dict)]
    return symbols, edges
