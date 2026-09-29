"""
Runtime call tracing for the accuracy harness.

The harness copies this file next to the repository it is about to trace and
imports it inside that repository's own interpreter, where the `saurix` package
does not exist. Nothing in this module may import Saurix, and nothing here may
raise at import time: a tracer that takes the test suite down with it produces
no ground truth at all.

An Observed Call is the pair (caller, callee) recorded for a call that really
executed, expressed as (module, qualified name) taken from the code object. The
comparison against inferred Edges happens outside the traced process.
"""

from __future__ import annotations

import atexit
import json
import os
import sys
from pathlib import Path

DIR_ENV = "SAURIX_TRACE_DIR"
ROOT_ENV = "SAURIX_TRACE_ROOT"
EXCLUDE_ENV = "SAURIX_TRACE_EXCLUDE"

# Calls are appended to disk in batches so a process that dies mid-run still
# leaves most of its trace behind.
BATCH = 200

# The name of the per-process status file. Its presence says the process
# started tracing, and its `finished` flag says it left through the exit path
# rather than being killed. A run with a process that never finished is
# reported as a truncated trace instead of a shorter one.
STATUS_SUFFIX = ".status.json"


def _enclosing_scope(qualname: str) -> str | None:
    """
    Reduce a qualified name to the named scope the graph has a symbol for.

    A lambda, a comprehension or a nested function has no symbol of its own, so
    the Indexing pipeline attributes the calls in its body to the enclosing
    function or method. Everything from the first generated component onwards is
    dropped: `Class.method.<locals>.helper` belongs to `Class.method`, and a
    `<lambda>` at module level belongs to nothing, because the pipeline emits
    no call edges from a module.
    """
    parts = qualname.split(".")
    for index, part in enumerate(parts):
        if "<" in part:
            parts = parts[:index]
            break
    return ".".join(parts) if parts else None


def _module_name(path: Path, root: Path, exclude: set[str]) -> str | None:
    """
    Return the repository-relative dotted module name of a source file.

    The excluded directory names are the ones the Indexing pipeline skips, so
    that the trace and the graph agree about which files exist.
    """
    if path.suffix != ".py":
        return None
    if not path.is_absolute():
        path = root / path
    try:
        rel = path.relative_to(root)
    except ValueError:
        return None
    if any(part in exclude for part in rel.parts):
        return None
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    if not parts:
        return None
    return ".".join(parts)


class CallTracer:
    """
    Records the calls that happen between symbols of one repository.

    A call is kept only when both ends are defined in the repository: a call
    into the standard library says nothing about the Edges inferred for this
    repository, and there is no symbol on the other side to match one against.
    """

    def __init__(self, directory: Path, root: Path, exclude: set[str]) -> None:
        self.directory = directory
        self.root = root
        self.exclude = exclude
        self.path = directory / f"calls-{os.getpid()}.jsonl"
        self.status = directory / f"calls-{os.getpid()}{STATUS_SUFFIX}"
        self._modules: dict[str, str | None] = {}
        self._pending: list[list[str]] = []
        self._recorded = 0
        self._error: str | None = None
        self._write_status()

    def module_for(self, filename: str) -> str | None:
        """
        Look up a file's module name, memoised because a hot loop asks the same
        question millions of times.
        """
        if filename not in self._modules:
            self._modules[filename] = _module_name(
                Path(filename), self.root, self.exclude
            )
        return self._modules[filename]

    def _callee(self, code: object) -> tuple[str, str] | None:
        module = self.module_for(getattr(code, "co_filename", ""))
        if module is None:
            return None
        return (module, code.co_qualname)  # type: ignore[attr-defined]

    def _caller(self, frame: object) -> tuple[str, str] | None:
        code = frame.f_code  # type: ignore[attr-defined]
        module = self.module_for(code.co_filename)
        if module is None:
            return None
        qualname = _enclosing_scope(code.co_qualname)
        if qualname is None:
            return None
        return (module, qualname)

    def profile(self, frame: object, event: str, arg: object) -> None:
        """
        The `sys.setprofile` hook. Only call events carry a callee.
        """
        if event != "call" or self._error is not None:
            return
        callee = self._callee(frame.f_code)  # type: ignore[attr-defined]
        if callee is None:
            return
        caller = self._caller(frame.f_back) if frame.f_back is not None else None  # type: ignore[attr-defined]
        if caller is None:
            return
        self._pending.append([*caller, *callee])
        if len(self._pending) >= BATCH:
            self.flush()

    def flush(self) -> None:
        """
        Append the pending calls to this process's trace file.

        A write that fails stops the trace rather than being swallowed. Carrying
        on would turn a broken measurement into a smaller one, and a smaller one
        still looks like a result.
        """
        if not self._pending:
            return
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                for row in self._pending:
                    handle.write(json.dumps(row) + "\n")
        except OSError as failure:
            self._error = f"the trace could not be written: {failure}"
            self._pending.clear()
            self._write_status()
            sys.setprofile(None)
            return
        self._recorded += len(self._pending)
        self._pending.clear()

    def _write_status(self) -> None:
        """
        Record what this process managed to trace, for the harness to check.
        """
        payload = {
            "pid": os.getpid(),
            "recorded": self._recorded,
            "error": self._error,
            "finished": False,
        }
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            self.status.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            pass

    def finish(self) -> None:
        """
        Flush and mark the process as having left through the exit path.
        """
        self.flush()
        payload = {
            "pid": os.getpid(),
            "recorded": self._recorded,
            "error": self._error,
            "finished": True,
        }
        try:
            self.status.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            pass


def install_from_env() -> None:
    """
    Start tracing if the harness asked for it. Used by the bootstrap shim.
    """
    raw_dir = os.environ.get(DIR_ENV)
    if not raw_dir:
        return
    directory = Path(raw_dir)
    root = Path(os.environ.get(ROOT_ENV, ".")).resolve()
    exclude = set(json.loads(os.environ.get(EXCLUDE_ENV, "[]")))
    tracer = CallTracer(directory, root, exclude)
    atexit.register(tracer.finish)
    sys.setprofile(tracer.profile)
