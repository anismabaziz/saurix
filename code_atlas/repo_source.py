from __future__ import annotations

import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse


_GITHUB_HOSTS = {"github.com", "www.github.com"}


def is_github_url(source: str) -> bool:
    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.netloc.lower() not in _GITHUB_HOSTS:
        return False
    parts = [p for p in parsed.path.split("/") if p]
    return len(parts) >= 2


def normalize_github_clone_url(source: str) -> tuple[str, str]:
    parsed = urlparse(source)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"Invalid GitHub repository URL: {source}")

    owner = parts[0]
    repo = parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]

    slug = f"{owner}/{repo}"
    clone_url = f"https://github.com/{slug}.git"
    return clone_url, slug


@contextmanager
def prepare_repo_source(source: str):
    candidate = Path(source).expanduser()
    if candidate.exists():
        yield candidate.resolve(), "local"
        return

    if not is_github_url(source):
        raise ValueError(
            f"Source does not exist locally and is not a supported GitHub URL: {source}"
        )

    clone_url, slug = normalize_github_clone_url(source)
    tmp_root = Path(tempfile.mkdtemp(prefix="code-atlas-"))
    clone_target = tmp_root / "repo"

    try:
        command = ["git", "clone", "--depth", "1", clone_url, str(clone_target)]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            details = stderr or stdout or "unknown git clone error"
            raise RuntimeError(f"Failed to clone {slug}: {details}")

        yield clone_target, f"github:{slug}"
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
