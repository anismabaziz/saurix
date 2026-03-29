from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from code_atlas.cache import DEFAULT_CACHE_PATH
from code_atlas.indexer import build_graph


@dataclass
class BenchRow:
    repo: str
    language_hint: str
    full_seconds: float
    incremental_seconds: float
    speedup_x: float
    cache_hits: int
    reindexed_files: int


REPOS: list[tuple[str, str, str]] = [
    ("pallets/flask", "https://github.com/pallets/flask.git", "python"),
    ("axios/axios", "https://github.com/axios/axios.git", "typescript"),
    ("google/gson", "https://github.com/google/gson.git", "java"),
]


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    bench_root = root / "tmp" / "bench"
    repos_dir = bench_root / "repos"
    graphs_dir = bench_root / "graphs"
    repos_dir.mkdir(parents=True, exist_ok=True)
    graphs_dir.mkdir(parents=True, exist_ok=True)

    rows: list[BenchRow] = []
    for slug, url, language_hint in REPOS:
        local_repo = ensure_clone(repos_dir, slug, url)
        clear_repo_cache(local_repo)

        full = timed_index(local_repo, graphs_dir / f"{slug.replace('/', '_')}.full.graph.json")
        inc = timed_index(local_repo, graphs_dir / f"{slug.replace('/', '_')}.inc.graph.json")

        full_s = full[0]
        inc_s = inc[0]
        speedup = round(full_s / inc_s, 2) if inc_s > 0 else 0.0
        inc_meta = inc[1].get("incremental_cache", {}) if isinstance(inc[1], dict) else {}

        rows.append(
            BenchRow(
                repo=slug,
                language_hint=language_hint,
                full_seconds=round(full_s, 2),
                incremental_seconds=round(inc_s, 2),
                speedup_x=speedup,
                cache_hits=int(inc_meta.get("cache_hits", 0)),
                reindexed_files=int(inc_meta.get("reindexed_files", 0)),
            )
        )

    markdown = build_markdown(rows)
    out = root / "docs" / "benchmarks.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"\nWrote benchmark report: {out}")


def ensure_clone(repos_dir: Path, slug: str, url: str) -> Path:
    local_repo = repos_dir / slug.replace("/", "__")
    if local_repo.exists():
        return local_repo

    local_repo.parent.mkdir(parents=True, exist_ok=True)
    command = ["git", "clone", "--depth", "1", url, str(local_repo)]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"clone failed: {url}")
    return local_repo


def clear_repo_cache(repo_root: Path) -> None:
    cache_file = repo_root / DEFAULT_CACHE_PATH
    if cache_file.exists():
        cache_file.unlink()
    bench_graph = repo_root / "tmp" / "code-atlas.graph.json"
    if bench_graph.exists():
        bench_graph.unlink()
    bench_tmp = repo_root / "tmp" / "bench"
    if bench_tmp.exists() and bench_tmp.is_dir():
        shutil.rmtree(bench_tmp)


def timed_index(repo_root: Path, out_graph: Path) -> tuple[float, dict[str, object]]:
    t0 = perf_counter()
    result = build_graph(repo_root)
    duration = perf_counter() - t0
    result.graph.write_json(out_graph)
    return duration, result.graph.stats()


def build_markdown(rows: list[BenchRow]) -> str:
    lines = [
        "# Benchmark Results",
        "",
        "Cold run = first run after cache clear. Warm run = immediate second run on same repo.",
        "",
        "| Repo | Lang | Full Index (s) | Incremental Re-index (s) | Speedup | Cache Hits | Reindexed Files |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| `{row.repo}` | {row.language_hint} | {row.full_seconds:.2f} | {row.incremental_seconds:.2f} | {row.speedup_x:.2f}x | {row.cache_hits} | {row.reindexed_files} |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
