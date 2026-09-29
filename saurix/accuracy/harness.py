"""
The accuracy harness.

One measured run, in order: check the target out at a pinned commit, build an
interpreter for it, run its test suite under the runtime trace, then index the
same checkout and diff the two. Every step that can fail returns a Comparison
carrying the reason instead of a figure, because a failed run reported as a
good score is the one failure mode worth engineering against.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ..core.config import config
from ..core.indexing import build_graph
from . import tracer as tracer_module
from .matching import Comparison, ObservedCall, Symbol, compare
from .report import NO_TRACE

BOOTSTRAP_NAME = "sitecustomize.py"
TRACER_NAME = "saurix_trace.py"

# How much of a failing test run's output to keep. Enough to see why, not so
# much that the report becomes a log.
LOG_TAIL = 12


@dataclass(frozen=True)
class Target:
    """
    The repository being measured, and how to run its test suite.

    `requirements` is the argument list handed to pip in the checkout, so a
    target can ask for whatever its own project declares: an editable install
    of the pinned source, its test extras, a requirements file, or none.
    """

    repository: str
    url: str
    commit: str
    test_command: tuple[str, ...]
    requirements: tuple[str, ...] = ("-e", ".")


class TraceFailure(Exception):
    """
    A step of the run that did not work. Carries the report's wording.
    """


def _run(
    command: list[str], cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _tail(completed: subprocess.CompletedProcess[str]) -> str:
    output = (completed.stdout or "") + (completed.stderr or "")
    lines = [line for line in output.splitlines() if line.strip()]
    return "\n".join(lines[-LOG_TAIL:])


def prepare_repository(target: Target, workdir: Path) -> Path:
    """
    Return a checkout of the target at its pinned commit, cloning it if needed.
    """
    repo = workdir / "repos" / target.repository.replace("/", "__")
    if not (repo / ".git").exists():
        repo.parent.mkdir(parents=True, exist_ok=True)
        completed = _run(
            ["git", "clone", "--filter=blob:none", target.url, str(repo)],
            cwd=workdir,
        )
        if completed.returncode != 0:
            raise TraceFailure(
                f"could not clone {target.repository}:\n{_tail(completed)}"
            )

    if target.commit:
        completed = _run(["git", "checkout", "--detach", target.commit], cwd=repo)
        if completed.returncode != 0:
            raise TraceFailure(
                f"could not check out {target.commit} of "
                f"{target.repository}:\n{_tail(completed)}"
            )

    completed = _run(["git", "rev-parse", "HEAD"], cwd=repo)
    if completed.returncode != 0:
        raise TraceFailure(f"could not read the commit of {target.repository}")
    return repo


def build_interpreter(repo: Path, target: Target, workdir: Path) -> Path:
    """
    Build a virtual environment with the target and its test dependencies.

    The environment lives outside the checkout: a `.venv` inside it would be
    scanned by the Indexing pipeline and buried in symbols that are not the
    target's.
    """
    venv = workdir / "venv"
    interpreter = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not interpreter.exists():
        completed = _run([sys.executable, "-m", "venv", str(venv)], cwd=workdir)
        if completed.returncode != 0:
            raise TraceFailure(
                f"could not build a virtual environment:\n{_tail(completed)}"
            )

    # The checkout, not the package index: the whole point of pinning a commit
    # is that the traced source is that commit and not whatever was released.
    completed = _run(
        [str(interpreter), "-m", "pip", "install", "-q", *target.requirements],
        cwd=repo,
    )
    if completed.returncode != 0:
        raise TraceFailure(
            f"could not install {target.repository} from its "
            f"checkout:\n{_tail(completed)}"
        )
    return interpreter


def trace_dir(workdir: Path) -> Path:
    """
    The directory the traced process appends its calls to.
    """
    return workdir / "trace"


def _write_bootstrap(workdir: Path) -> Path:
    """
    Drop the tracer and the startup shim where the child interpreter finds them.
    """
    directory = workdir / "bootstrap"
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(tracer_module.__file__), directory / TRACER_NAME)
    shutil.copyfile(Path(__file__).parent / "bootstrap.py", directory / BOOTSTRAP_NAME)
    return directory


def run_traced_suite(
    *,
    interpreter: Path,
    test_command: tuple[str, ...],
    repository: str,
    repo: Path,
    workdir: Path,
) -> Path:
    """
    Run the target's test suite under the trace, and return the trace directory.
    """
    traces = trace_dir(workdir)
    if traces.exists():
        shutil.rmtree(traces)
    traces.mkdir(parents=True)

    bootstrap = _write_bootstrap(workdir)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(bootstrap), str(repo), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    env[tracer_module.DIR_ENV] = str(traces)
    env[tracer_module.ROOT_ENV] = str(repo)
    env[tracer_module.EXCLUDE_ENV] = json.dumps(sorted(config.exclude_dirs))

    completed = _run([str(interpreter), *test_command], cwd=repo, env=env)
    if completed.returncode != 0:
        raise TraceFailure(
            f"`{' '.join(test_command)}` exited {completed.returncode} "
            f"in {repository}:\n{_tail(completed)}"
        )
    return traces


def check_trace_health(traces: Path) -> None:
    """
    Refuse a trace that is known to be incomplete.

    Every traced process leaves a status file saying whether it reached the end
    of the run and whether it managed to write. A process that recorded calls
    and then vanished took part of the trace with it, and the numbers below
    would be quietly low rather than wrong-looking. A process that recorded
    nothing and was killed lost nothing, so it is not treated as a problem.
    """
    problems: list[str] = []
    for path in sorted(traces.glob(f"*{tracer_module.STATUS_SUFFIX}")):
        try:
            status = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            problems.append(f"{path.name} could not be read")
            continue
        if status.get("error"):
            problems.append(f"process {status.get('pid')}: {status['error']}")
        elif not status.get("finished") and status.get("recorded"):
            problems.append(
                f"process {status.get('pid')} was killed after recording "
                f"{status['recorded']} calls, so the trace is truncated"
            )
    if problems:
        raise TraceFailure(
            "the trace is not complete:\n" + "\n".join(f"- {p}" for p in problems)
        )


def load_observed(traces: Path) -> list[ObservedCall]:
    """
    Read the trace files every traced process left behind, de-duplicated.
    """
    seen: set[tuple[Symbol, Symbol]] = set()
    for path in sorted(traces.glob("calls-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            caller_module, caller_qualname, callee_module, callee_qualname = json.loads(
                line
            )
            seen.add(
                (
                    Symbol(module=caller_module, qualname=caller_qualname),
                    Symbol(module=callee_module, qualname=callee_qualname),
                )
            )
    return [
        ObservedCall(caller=caller, callee=callee)
        for caller, callee in sorted(seen, key=lambda pair: f"{pair[0]}{pair[1]}")
    ]


def run_accuracy(
    target: Target,
    workdir: Path,
    *,
    interpreter: Path | None = None,
    install: bool = True,
) -> Comparison:
    """
    Measure the target once and return the comparison, failed runs included.
    """
    command = " ".join(target.test_command)
    commit = target.commit
    try:
        repo = prepare_repository(target, workdir)
        commit = _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
        if interpreter is None:
            if not install:
                raise TraceFailure("no interpreter given and installation turned off")
            interpreter = build_interpreter(repo, target, workdir)
        traces = run_traced_suite(
            interpreter=interpreter,
            test_command=target.test_command,
            repository=target.repository,
            repo=repo,
            workdir=workdir,
        )
        check_trace_health(traces)
        observed = load_observed(traces)
        if not observed:
            raise TraceFailure(NO_TRACE)
        graph = build_graph(repo).graph
    except TraceFailure as failure:
        return Comparison(
            repository=target.repository,
            commit=commit,
            test_command=command,
            failure=str(failure),
        )

    return compare(
        repository=target.repository,
        commit=commit,
        test_command=command,
        observed=observed,
        graph=graph,
    )
