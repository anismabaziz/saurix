from __future__ import annotations

"""
Shared flag parsing helpers for CLI commands.

Centralizes parsing for ``--limit``, ``--depth``, ``--max-depth``,
``--exclude``, and ``--out`` so commands do not duplicate logic and
defaults stay consistent.
"""

from pathlib import Path


def parse_int_flag(parts: list[str], flag: str, default: int) -> int | None:
    """
    Parse optional integer flag value from command tokens.
    """
    if flag not in parts:
        return default
    try:
        return int(parts[parts.index(flag) + 1])
    except (IndexError, ValueError):
        return None


def parse_csv_flag(parts: list[str], flag: str) -> set[str] | None:
    """
    Parse optional CSV flag (e.g. ``--exclude dir1,dir2``).
    """
    if flag not in parts:
        return None
    try:
        raw = parts[parts.index(flag) + 1]
    except IndexError:
        return None
    entries = {chunk.strip() for chunk in raw.split(",") if chunk.strip()}
    return entries or None


def parse_path_flag(parts: list[str], flag: str, default: Path) -> Path:
    """
    Parse optional path flag value from command tokens.
    """
    if flag not in parts:
        return default.resolve()
    try:
        return Path(parts[parts.index(flag) + 1]).resolve()
    except IndexError:
        return default.resolve()
