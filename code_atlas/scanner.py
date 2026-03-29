from __future__ import annotations

from pathlib import Path


DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "target",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".idea",
    ".vscode",
}

LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".kt": "kotlin",
    ".swift": "swift",
}


def detect_language(path: Path) -> str | None:
    return LANGUAGE_BY_EXTENSION.get(path.suffix.lower())


def should_skip(path: Path, root: Path, exclude_dirs: set[str]) -> bool:
    rel = path.relative_to(root)
    return any(part in exclude_dirs for part in rel.parts)


def scan_source_files(root: Path, exclude_dirs: set[str] | None = None) -> list[Path]:
    excludes = exclude_dirs or DEFAULT_EXCLUDE_DIRS
    files: list[Path] = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if should_skip(path, root, excludes):
            continue
        if detect_language(path) is None:
            continue
        files.append(path)

    return sorted(files)
