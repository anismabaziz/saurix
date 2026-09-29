"""
Rendering of the accuracy report.

The report is the whole point of the harness, so it carries its own method: a
reader who has never read the code has to be able to tell what was measured,
what the figure covers, and what it does not.
"""

from __future__ import annotations

import textwrap

from .matching import ROW_LIMIT, Call, Comparison, InferredEdge, UnresolvedEdge

WIDTH = 79

INTRO = """\
A target repository is checked out at a pinned commit and its own test suite
is run under a runtime trace. The trace records an Observed Call for every call
that really happens between two of the repository's own symbols: evidence that
a call happened, not that it was possible. The same checkout is then indexed,
and each Observed Call is matched against a CALLS edge naming the same two
symbols."""

FIGURE = """\
The figure is precision on observed edges: the share of calls that really
happened which the Indexing pipeline also inferred. A call into the standard
library is not counted, because there is no symbol in this repository on the
other side to match it against."""

LIMITS = """\
Three things follow from tracing, and each one is visible in the tables below.
A call through a function pointer is recorded but cannot be resolved statically,
so it lands in the miss table; that is a real limit of inference rather than a
defect in the measurement. A call made from a lambda or a nested function is
attributed to the enclosing named scope, which is what the Indexing pipeline
does too. A test that passes without ever calling the code under it leaves an
inferred edge with nothing to confirm it."""

NAMING = """\
One caveat belongs with the figure rather than beside it. A caller is named by
the file it sits in, which is what the graph does too, but a callee is named by
the import statement that reached it. In a repository that keeps its package
under `src/`, those two conventions give the same symbol two different names, so
a call across that boundary is recorded as a miss even when the pipeline found
it. This lowers the number below; nothing has been done to raise it."""

NO_RECALL = """\
Recall is not measured here and none is claimed. An inferred edge the trace
never saw is not a false negative: it is an edge on a path the test suite did
not execute, and counting it as a miss would understate the tool for the wrong
reason."""

NO_TRACE = """\
The trace recorded no calls between repository symbols, so no figure is
reported. A run that could not be measured is not a run with a good score."""


def _percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def _wrap(text: str) -> list[str]:
    """Wrap a paragraph to the report's line width."""
    return textwrap.wrap(text, width=WIDTH)


def _table(rows: list[str], total: int) -> list[str]:
    """
    Render a bounded table, saying out loud when rows were left out.
    """
    if not rows:
        return ["None.", ""]
    shown = rows[:ROW_LIMIT]
    lines = ["| Caller | Callee | Where |", "| :--- | :--- | :--- |", *shown]
    if total > len(shown):
        lines += [
            "",
            *_wrap(
                f"Showing {len(shown)} of {total}. The rest are in the trace file "
                "and the graph JSON this run produced."
            ),
        ]
    lines.append("")
    return lines


def _call_rows(calls: tuple[Call, ...]) -> list[str]:
    return [
        f"| `{call.caller.render()}` | `{call.callee.render()}` | - |" for call in calls
    ]


def _inferred_rows(edges: tuple[InferredEdge, ...]) -> list[str]:
    return [
        f"| `{edge.caller.render()}` | `{edge.callee.render()}` | "
        f"`{edge.file or '?'}:{edge.line or 0}` ({edge.confidence}) |"
        for edge in edges
    ]


def _unresolved_rows(edges: tuple[UnresolvedEdge, ...]) -> list[str]:
    return [
        f"| `{edge.caller}` | `{edge.target}` | `{edge.file or '?'}:{edge.line or 0}` |"
        for edge in edges
    ]


def _method() -> list[str]:
    return [
        "## Method",
        "",
        *_wrap(INTRO),
        "",
        *_wrap(FIGURE),
        "",
        *_wrap(LIMITS),
        "",
        *_wrap(NAMING),
        "",
        *_wrap(NO_RECALL),
        "",
    ]


def _breakdown(comparison: Comparison) -> list[str]:
    """
    Split the misses into the shapes that produce them, so the figure above is
    readable rather than merely small.
    """
    return [
        "Every one of them comes from one of three shapes:",
        "",
        f"- the pipeline recorded the call but could not name its target "
        f"({comparison.missed_from_unresolved}). A call through a parameter, "
        "through `super()`, or through an attribute of an instance looks like "
        "this.",
        f"- the call landed on a method a subclass overrides "
        f"({comparison.missed_to_override}). The pipeline names the method the "
        "class declares and the trace names the one that answered; both are "
        "right, and they are not the same edge.",
        "- the pipeline recorded no call for the caller at all "
        f"({comparison.missed_from_silent}).",
        "",
    ]


def _result(comparison: Comparison) -> list[str]:
    precision = comparison.precision
    figure = _percent(precision) if precision is not None else "not measured"
    return [
        "## Result",
        "",
        "| Repository | Commit | Test command | Observed calls | Matched | Precision |",
        "| :--- | :--- | :--- | ---: | ---: | ---: |",
        f"| `{comparison.repository}` | `{comparison.commit[:12]}` | "
        f"`{comparison.test_command}` | {comparison.observed_total} | "
        f"{comparison.matched_count} | {figure} |",
        "",
    ]


def _failure(reason: str) -> list[str]:
    return [
        "## This run failed",
        "",
        *_wrap(NO_TRACE),
        "",
        "```",
        reason,
        "```",
        "",
    ]


def render_markdown(comparison: Comparison) -> str:
    """
    Render one measured run as the published report.
    """
    lines = [
        "# Saurix Call Edge Accuracy",
        "",
        "Generated by `scripts/accuracy.py`. Regenerate it with:",
        "",
        "```",
        "uv run scripts/accuracy.py",
        "```",
        "",
        *_method(),
        *_result(comparison),
    ]

    precision = comparison.precision
    if precision is None:
        lines += _failure(comparison.failure or NO_TRACE)
        return "\n".join(lines).rstrip() + "\n"

    lines += [
        *_wrap(
            f"{comparison.matched_count} of {comparison.observed_total} observed "
            f"calls were also inferred as Edges: **{_percent(precision)}**."
        ),
        "",
        *_wrap(
            f"The graph holds {comparison.inferred_total} CALLS edges, of which "
            f"{comparison.judgeable_total} name a symbol this repository defines and "
            f"could be judged either way. The other "
            f"{comparison.unresolved_count} are listed at the bottom."
        ),
        "",
        "## Observed calls with no inferred edge",
        "",
        *_wrap(
            f"Calls that really happened and the graph does not contain: "
            f"{len(comparison.unmatched_observed)} of {comparison.observed_total}."
        ),
        "",
        *_breakdown(comparison),
        *_table(
            _call_rows(comparison.unmatched_observed),
            len(comparison.unmatched_observed),
        ),
        "## Inferred edges the trace never saw",
        "",
        *_wrap(
            "Edges between two symbols of the repository that no observed call "
            f"matched: {len(comparison.unobserved_inferred)} of "
            f"{comparison.judgeable_total} judgeable. Each is either dead code or a "
            "path the test suite does not reach, and this run cannot tell which."
        ),
        "",
        *_table(
            _inferred_rows(comparison.unobserved_inferred),
            len(comparison.unobserved_inferred),
        ),
        "## Inferred edges pointing outside the repository",
        "",
        *_wrap(
            f"Edges whose target is a name nothing in the repository defines: "
            f"{comparison.unresolved_count} of {comparison.inferred_total}. The "
            "trace can neither confirm nor deny a call to something the graph has no "
            "record of, so these are counted apart from the figure above."
        ),
        "",
        *_table(
            _unresolved_rows(comparison.unresolved_edges),
            comparison.unresolved_count,
        ),
    ]
    return "\n".join(lines).rstrip() + "\n"
