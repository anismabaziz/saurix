"""
The hand-labeled sample.

A runtime trace only sees the paths a test suite executes. This module covers
the rest: a region of the target repository that nobody runs, read by hand and
written down one call per line, then diffed against the Edges the Indexing
pipeline inferred there. It is a separate measurement with its own figure, not
a second opinion on the first one, so nothing in here is averaged with the
trace's result.

A label file is a plain text file. Every non-blank, non-comment line names one
call the way the graph names it:

    <file>:<qualified name> -> <callee>

The callee is written the way the target wrote it: a bare `pkg.mod.name` for a
call the pipeline could not resolve, `pkg.mod:Class.method` for one it could.
Writing it down this way is deliberate. A label is either the edge the pipeline
inferred or it is not, and no amount of near-miss counting goes into the figure.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ..core.graph import GraphStore
from .matching import symbol_key

# `file.py:qualname -> callee`. The arrow and the colon are the only structure,
# so a file path containing either would need quoting; a repository's source
# paths do not.
ARROW = "->"
COMMENT = "#"

# How many rows a sample table the report prints before it starts counting.
ROW_LIMIT = 25


@dataclass(frozen=True)
class EdgeKey:
    """
    One call edge, named the way both the labels and the graph name it.

    A label and an inferred edge are the same shape: a file, a qualified name,
    and a callee. Keeping one type for both means a match is a set membership
    test rather than a comparison of three loose strings, and the report cannot
    print one end of a comparison the other end does not have.
    """

    caller_file: str
    caller_qualname: str
    callee: str

    def render(self) -> str:
        """Render it the way the report does, one edge per cell."""
        return f"`{self.caller_file}:{self.caller_qualname}` -> `{self.callee}`"

    @property
    def key(self) -> EdgeKey:
        """
        This edge as the bare value two subclasses are compared through.

        A `Label` and an `InferredInRegion` are different facts about one call,
        so dataclass equality will not pair them. Going through the base type is
        what makes a label and an edge comparable at all.
        """
        return EdgeKey(self.caller_file, self.caller_qualname, self.callee)


@dataclass(frozen=True)
class Label(EdgeKey):
    """
    One call a person confirmed by reading the code.
    """


@dataclass(frozen=True)
class InferredInRegion(EdgeKey):
    """
    A CALLS edge the pipeline inferred from inside a labeled file.

    `resolved` says whether the callee names a symbol the graph defines. It is
    kept because a region of example code is mostly calls to a library the
    repository does not define, and a figure over such a region says something
    narrower than a reader might assume. The report needs to say so out loud.
    """

    file: str | None = None
    line: int | None = None
    confidence: str = "medium"
    resolved: bool = False


@dataclass(frozen=True)
class LabeledSample:
    """
    A hand-labeled region, and the file it was read into.
    """

    path: Path
    labels: tuple[Label, ...]

    @property
    def files(self) -> tuple[str, ...]:
        """The files the sample covers, in the order a reader would list them."""
        return _ordered_files(self.labels)

    @property
    def pairs(self) -> set[EdgeKey]:
        """
        The labeled edges as a set, so matching does not depend on the order
        they were written in.
        """
        return {label.key for label in self.labels}


@dataclass(frozen=True)
class SampleCheck:
    """
    One checked sample: what a person wrote down, and what the pipeline holds.
    """

    confirmed: tuple[InferredInRegion, ...]
    unconfirmed: tuple[InferredInRegion, ...]
    missing: tuple[Label, ...]

    @property
    def files(self) -> tuple[str, ...]:
        """The files the sample covers."""
        return _ordered_files(self.confirmed)

    @property
    def label_total(self) -> int:
        """How many edges were hand-labeled."""
        return len(self.confirmed) + len(self.missing)

    @property
    def inferred_in_region(self) -> int:
        """
        How many Edges the pipeline inferred from the labeled files. This is the
        denominator: an edge pointing at a name the pipeline could not resolve
        still counts, because the hand reader is asked whether the call is there
        whatever the graph managed to call its target.
        """
        return len(self.confirmed) + len(self.unconfirmed)

    @property
    def unresolved_in_region(self) -> int:
        """
        How many of those edges name a callee the graph does not define.

        High in an example directory, and the report has to say so: a high
        precision figure over edges that were never resolved is a narrower claim
        than it looks, and a reader who does not know that will read it as a
        wider one.
        """
        return sum(1 for edge in self.confirmed if not edge.resolved) + sum(
            1 for edge in self.unconfirmed if not edge.resolved
        )

    @property
    def precision(self) -> float:
        """
        The share of inferred edges in the region a person confirmed.

        Same definition as the trace's figure, different population: here the
        ground truth is a reading of the source, not a call that really
        happened, so a call through a variable the pipeline could not follow
        lands here as a miss and would have landed in the trace as a hit.
        """
        if not self.inferred_in_region:
            return 0.0
        return len(self.confirmed) / self.inferred_in_region


def _ordered_files(edges: Iterable[EdgeKey]) -> tuple[str, ...]:
    """
    The distinct caller files of some edges, in first-seen order.

    First-seen rather than sorted, so the report lists the files in the order a
    person read them and a reader can follow along.
    """
    seen: list[str] = []
    for edge in edges:
        if edge.caller_file not in seen:
            seen.append(edge.caller_file)
    return tuple(seen)


def _parse_line(line: str, number: int, path: Path) -> Label:
    """
    Read one label, refusing anything this file's format cannot express.
    """
    where = f"{path.name}:{number}"
    if ARROW not in line:
        raise ValueError(
            f"{where}: expected `{ARROW}` between the caller and the callee, "
            f"got {line!r}"
        )
    caller, _, callee = line.partition(ARROW)
    caller = caller.strip()
    callee = callee.strip()
    if ":" not in caller:
        raise ValueError(f"{where}: the caller must be `file.py:qualified name`")
    caller_file, _, caller_qualname = caller.rpartition(":")
    caller_file = caller_file.strip()
    caller_qualname = caller_qualname.strip()
    if not caller_file or not caller_qualname:
        raise ValueError(f"{where}: the caller must name a file and a symbol")
    if not callee:
        raise ValueError(f"{where}: the callee is missing")
    return Label(
        caller_file=caller_file, caller_qualname=caller_qualname, callee=callee
    )


def load_sample(path: Path) -> LabeledSample:
    """
    Read a hand-labeled sample from disk.

    Every line is either a comment, blank, or one call. A line that is none of
    those is an error naming the file and the line, because a label file that
    silently drops half its rows is a sample nobody can check.
    """
    labels: list[Label] = []
    for number, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw.strip()
        if not line or line.startswith(COMMENT):
            continue
        labels.append(_parse_line(line, number, path))
    if not labels:
        raise ValueError(f"{path.name}: the sample is empty")
    return LabeledSample(path=path, labels=tuple(labels))


def _strip_scheme(symbol_id: str) -> str:
    """
    A symbol id without its scheme, which is how a label writes it.
    """
    return symbol_id.split("://", 1)[-1]


def _in_region(sample: LabeledSample, graph: GraphStore) -> list[InferredInRegion]:
    """
    Every CALLS edge whose caller sits in a labeled file, with whether its
    callee names something the graph defines.
    """
    files = set(sample.files)
    defined = {
        _strip_scheme(symbol.id)
        for symbol in graph.symbols.values()
        if symbol.file is not None and symbol_key(symbol.id) is not None
    }
    inferred: list[InferredInRegion] = []
    for edge in graph.get_edges_by_type("CALLS"):
        if edge.file not in files:
            continue
        reduced = symbol_key(edge.source)
        if reduced is None:
            continue
        callee = _strip_scheme(edge.target)
        inferred.append(
            InferredInRegion(
                caller_file=edge.file,
                caller_qualname=reduced.qualname,
                callee=callee,
                file=edge.file,
                line=edge.line,
                confidence=edge.confidence,
                resolved=callee in defined,
            )
        )
    return inferred


def compare_sample(sample: LabeledSample, graph: GraphStore) -> SampleCheck:
    """
    Diff the hand-labeled sample against the Edges inferred in the same files.

    Three outcomes, all kept: an inferred edge a label confirms, an inferred
    edge no label accounts for, and a label the graph does not hold. Dropping
    the last one would make a pipeline that inferred nothing score perfectly on
    a region nobody checked, which is the one result this measurement exists to
    rule out.
    """
    labeled = sample.pairs
    inferred = _in_region(sample, graph)

    confirmed: list[InferredInRegion] = []
    unconfirmed: list[InferredInRegion] = []
    matched: set[EdgeKey] = set()
    seen: set[EdgeKey] = set()
    for edge in sorted(inferred, key=lambda e: (e.render(), e.line or 0)):
        if edge.key in seen:
            # The same call written at two call sites is one edge, and a person
            # labeling the source would have written it down once. Counting it
            # twice would weight the figure by how often a call is repeated.
            continue
        seen.add(edge.key)
        if edge.key in labeled:
            confirmed.append(edge)
            matched.add(edge.key)
        else:
            unconfirmed.append(edge)

    missing = tuple(label for label in sample.labels if label.key not in matched)
    return SampleCheck(
        confirmed=tuple(confirmed),
        unconfirmed=tuple(unconfirmed),
        missing=missing,
    )
