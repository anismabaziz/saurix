"""
Rendering of the accuracy report.

The report is the whole point of the harness, so it carries its own method: a
reader who has never read the code has to be able to tell what was measured,
what the figure covers, what it does not, and where the tool is wrong. It leads
with the number and the commit it was measured at, then explains itself, then
shows the evidence.
"""

from __future__ import annotations

import textwrap
from collections.abc import Iterable

from .harness import Measurement
from .labels import InferredInRegion, SampleCheck
from .matching import (
    NO_TRACE,
    ROW_LIMIT,
    Call,
    Comparison,
    InferredEdge,
    UnresolvedEdge,
)

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

SAMPLE_INTRO = """\
A trace can only judge the paths a test suite runs. Where the suite does not
reach, the ground truth has to come from somewhere else, so a region of the
target that no test executes was read by hand and every call written down, one
per line, in a committed file next to this report. The Edges the pipeline
inferred in those files are then diffed against that list."""

SAMPLE_SCOPE = """\
A sample figure much higher than the trace figure is not the tool being better
than the trace suggests. It is a different question. The trace counts every call
a test suite makes, including the ones a person would never write down: a
decorator on a parameter, a method reached through an instance, a helper
reached only in production. The sample counts a region of ordinary module-level
code read once, top to bottom. It is a smaller and easier population, and a high
figure on it says the pipeline handles ordinary code well. It does not say the
pipeline handles the calls a test suite makes well."""

SAMPLE_UNRESOLVED = """\
What the sample cannot tell you is where those calls land. Every edge in this
region points at a name the repository does not define: `click.echo`,
`os.listdir`, `urlparse.urlparse`. The pipeline read the source, wrote down the
dotted name it found there, and stopped. So this figure says the calls were
found and written down accurately. It says nothing about whether the target
would have been resolved to the right symbol if the code had been able to. The
trace figure above is the one that exercises that step, because a call that
really happened has a real callee to match against."""

SAMPLE_NO_FIGURE = """\
No hand-labeled sample was supplied for this run, so only the trace figure is
reported. A region nobody read is not a region with a score."""

WEAK_LANGUAGES = """\
Only Python is traced. Go, Java and TypeScript are indexed by the same
pipeline, but no runtime evidence is collected for them, so this report says
nothing at all about how well those edges are inferred. The figure below is a
statement about Python and should not be read as a statement about the tool."""

WEAK_SHAPES_LEAD = """\
The call shapes where the pipeline is weakest, all of them visible in the tables
below:"""

WEAK_SHAPES = [
    "A call through a variable, a parameter, or an attribute of an instance. The "
    "call is there; the pipeline cannot know what the name holds. This is the "
    "single largest source of misses.",
    "A call made from a decorator, a lambda, or a comprehension. The call is "
    "attributed to the enclosing named scope rather than to the anonymous "
    "function that makes it.",
    "A call whose target is a subclass override. The pipeline names the method "
    "the class declares, the trace names the one that answered. Both are right "
    "and they are not the same edge.",
    "A call across a package boundary, where the callee is named by the import "
    "that reached it rather than by the file it lives in.",
]

SNAPSHOT = """\
This is a published snapshot, not a CI gate. Nothing fails a build on it. The
target is a foreign repository whose suite needs its own dependencies, pinned to
one commit, which is a slow and fragile thing to hang on every push. Promoting
it to a scheduled check would need three things this project does not have yet:
a container image so the run does not depend on the machine, a recorded floor
for the figure so a regression is a failure rather than a surprise, and a
maintained list of targets rather than the single one measured here."""


def _percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def _wrap(text: str) -> list[str]:
    """Wrap a paragraph to the report's line width."""
    return textwrap.wrap(text, width=WIDTH)


def _bullets(items: list[str]) -> list[str]:
    """
    Render a list as list items rather than one wrapped paragraph: a bulleted
    claim a reader has to re-read three times to find the dashes in is a claim
    nobody reads.
    """
    return [f"- {item}" for item in items]


def _table(rows: list[str], total: int, header: str, where: str) -> list[str]:
    """
    Render a bounded table, saying out loud when rows were left out and where
    the ones left out are.

    One renderer for both tables in the report. They were near-identical when
    there were two, and a reader comparing the sections should not have to work
    out why one of them behaves differently.
    """
    if not rows:
        return ["None.", ""]
    shown = rows[:ROW_LIMIT]
    columns = header.split(" | ")
    lines = [
        f"| {' | '.join(columns)} |",
        f"| {' | '.join(':' + '-' * (len(c) - 1) for c in columns)} |",
        *shown,
    ]
    if total > len(shown):
        lines += [
            "",
            *_wrap(
                f"Showing {len(shown)} of {total}. The rest are in {where} and "
                "the graph JSON this run produced."
            ),
        ]
    lines.append("")
    return lines


TRACE_HEAD = "Caller | Callee | Where"
SAMPLE_HEAD = "Edge | Inferred at"
TRACE_WHERE = "the trace file"


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


def _summary(comparison: Comparison) -> list[str]:
    """
    The figure, the commit it was measured at, and the command that produced
    it. This is what a reader who stops here has, so it comes before anything
    else. A run with no figure says so and states nothing that could be read
    as a score.
    """
    precision = comparison.precision
    figure = _percent(precision) if precision is not None else "not measured"
    lines = [
        "## Result",
        "",
        "### Precision on observed calls",
        "",
        f"**{figure}**",
        "",
    ]
    if precision is not None:
        lines += _wrap(
            f"{comparison.repository} at `{comparison.commit}`, measured by "
            f"tracing its test suite with `{comparison.test_command}`. "
            f"{comparison.matched_count} of {comparison.observed_total} observed "
            "calls were also inferred as Edges."
        )
        lines.append("")
    lines += [
        "| Repository | Commit | Test command | Observed calls | Matched | Precision |",
        "| :--- | :--- | :--- | ---: | ---: | ---: |",
        f"| `{comparison.repository}` | `{comparison.commit[:12]}` | "
        f"`{comparison.test_command}` | {comparison.observed_total} | "
        f"{comparison.matched_count} | {figure} |",
        "",
    ]
    return lines


def _sample_files(check: SampleCheck) -> str:
    """
    The files a sample covers, as one inline span.
    """
    return ", ".join(f"`{name}`" for name in check.files)


def _sample_rows(edges: Iterable[InferredInRegion]) -> list[str]:
    """
    Render inferred edges from the sample as rows, with where they were found.
    """
    return [
        f"| {edge.render()} | "
        f"`{edge.file or '?'}:{edge.line or 0}` ({edge.confidence}) |"
        for edge in edges
    ]


def _sample_section(check: SampleCheck | None) -> list[str]:
    """
    The second figure, over a region no test executes.

    It is reported beside the first rather than folded into it: the two
    populations are different, and averaging them would produce a number that
    describes neither.
    """
    lines = [
        "## The hand-labeled sample",
        "",
        *_wrap(SAMPLE_INTRO),
        "",
    ]
    if check is None:
        lines += [*_wrap(SAMPLE_NO_FIGURE), ""]
        return lines

    files = len(check.files)
    noun = "file" if files == 1 else "files"
    labels = check.label_total
    label_noun = "edge" if labels == 1 else "edges"
    lines += [
        "### Precision on the hand-labeled sample",
        "",
        f"**{_percent(check.precision)}**",
        "",
        *_wrap(
            f"The sample covers {files} {noun} of the target "
            f"({_sample_files(check)}), which no test in the suite executes, "
            f"holding {labels} hand-labeled {label_noun}. Every call in those "
            "files was written down by reading them; the method is at the top of "
            "the label file, and it can be disagreed with."
        ),
        "",
        *_wrap(
            f"The pipeline inferred {check.inferred_in_region} CALLS edges from "
            f"them and {len(check.confirmed)} of those are in the labels. The two "
            "figures are not combined: they are different populations, measured "
            "by different means, and averaging them would describe neither."
        ),
        "",
        *_wrap(SAMPLE_SCOPE),
        "",
        *_wrap(
            f"None of the {check.inferred_in_region} is resolved: every one "
            "points at a name the graph does not define."
            if check.unresolved_in_region == check.inferred_in_region
            else (
                f"{check.unresolved_in_region} of the "
                f"{check.inferred_in_region} point at a name the graph does not "
                "define."
            )
        ),
        "",
        *_wrap(SAMPLE_UNRESOLVED),
        "",
        "### Inferred edges in the sample the labels do not confirm",
        "",
        *_wrap(
            f"{len(check.unconfirmed)} of {check.inferred_in_region}. A person "
            "reading the source found no such call, so the pipeline recorded a "
            "call that is not there."
        ),
        "",
        *_table(
            _sample_rows(check.unconfirmed),
            len(check.unconfirmed),
            SAMPLE_HEAD,
            "the label file",
        ),
        "### Labeled calls the graph does not hold",
        "",
        *_wrap(
            f"{len(check.missing)} of {labels}. The call is in the source and the "
            "graph does not contain it. These are listed rather than folded into "
            "the figure above, because a hand label says a call is reachable, "
            "not that anything calls it."
        ),
        "",
        *_table(
            [f"| {label.render()} | - |" for label in check.missing],
            len(check.missing),
            SAMPLE_HEAD,
            "the label file",
        ),
    ]
    return lines


def _weaknesses() -> list[str]:
    """
    Where the tool is weakest, so the figure is read with its limits in hand.
    """
    return [
        "## Where the tool is weakest",
        "",
        *_wrap(WEAK_LANGUAGES),
        "",
        *_wrap(WEAK_SHAPES_LEAD),
        "",
        *_bullets(WEAK_SHAPES),
        "",
    ]


def _snapshot() -> list[str]:
    """
    What this document is, and what would have to change for it to be a gate.
    """
    return [
        "## What this is",
        "",
        *_wrap(SNAPSHOT),
        "",
    ]


def _failure(reason: str) -> list[str]:
    """
    A run that could not be measured, shown as such.
    """
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


def render_markdown(measurement: Measurement) -> str:
    """
    Render one measured run as the published report.

    It takes the `Measurement` rather than its two parts so the sample figure
    cannot be rendered for one run while the trace figure comes from another.
    """
    comparison = measurement.comparison
    sample = measurement.sample
    lines = [
        "# Saurix Call Edge Accuracy",
        "",
        "Generated by `scripts/accuracy.py`. Regenerate it with:",
        "",
        "```",
        "uv run scripts/accuracy.py",
        "```",
        "",
        *_summary(comparison),
    ]

    precision = comparison.precision
    if precision is None:
        lines += _failure(comparison.failure or NO_TRACE)
        return "\n".join(lines).rstrip() + "\n"

    lines += [
        *_wrap(
            f"The graph holds {comparison.inferred_total} CALLS edges, of which "
            f"{comparison.judgeable_total} name a symbol this repository defines and "
            f"could be judged either way. The other "
            f"{comparison.unresolved_count} are listed at the bottom."
        ),
        "",
        *_sample_section(sample),
        *_method(),
        *_weaknesses(),
        *_snapshot(),
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
            TRACE_HEAD,
            TRACE_WHERE,
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
            TRACE_HEAD,
            TRACE_WHERE,
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
            TRACE_HEAD,
            TRACE_WHERE,
        ),
    ]
    return "\n".join(lines).rstrip() + "\n"
