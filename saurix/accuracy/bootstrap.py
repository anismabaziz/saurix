"""
Bootstrap shim for the traced process.

The harness copies this file into a work directory under the name
`sitecustomize.py` and puts that directory on the child's `PYTHONPATH`. Python
imports `sitecustomize` during startup, which is the earliest point at which a
foreign interpreter can be told to start tracing. It has to be that early:
a profiler installed after the test session has already collected its modules
misses the imports and the fixtures those tests build on.

The file is also importable as a plain module, which is how the tests read it.
It may not import Saurix: it runs in the target repository's interpreter.
"""

from __future__ import annotations

import os
import sys

SHIM_ENV = "SAURIX_TRACE_DIR"


def _chain_previous_shim() -> None:
    """
    Run the sitecustomize this interpreter would have imported without us.

    Ours shadows theirs by being earlier on the path, and a test suite that
    depends on its own sitecustomize should not lose it to the harness.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    for entry in sys.path:
        if not entry or os.path.abspath(entry) == here:
            continue
        candidate = os.path.join(entry, "sitecustomize.py")
        if os.path.isfile(candidate):
            try:
                with open(candidate, encoding="utf-8") as handle:
                    exec(
                        compile(handle.read(), candidate, "exec"),
                        {"__file__": candidate},
                    )
            except Exception:
                pass
            return


if os.environ.get(SHIM_ENV):
    try:
        # Imported under that name only in the traced process, where this file
        # is copied next to it.
        import saurix_trace  # type: ignore[import-not-found]

        saurix_trace.install_from_env()
    except Exception:
        pass
    _chain_previous_shim()
