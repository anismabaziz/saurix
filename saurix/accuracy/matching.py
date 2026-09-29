"""
Comparison of runtime truth against inferred Edges.

The trace speaks in (module, qualified name) pairs and the graph speaks in
symbol ids like `python://calculator.report:label`. `symbol_key` reduces the
graph's vocabulary to the trace's so the two can be compared on equal terms,
and `compare` does the comparison and keeps both sides' leftovers visible.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ..core.graph import GraphStore

SCHEME = "python://"

# How many rows a table in the report shows before it starts counting instead.
ROW_LIMIT = 25


@dataclass(frozen=True)
class Symbol:
    """
    One symbol of one repository: the module it lives in and its qualified name.
    """

    module: str
    qualname: str

    def render(self) -> str:
        """Render it the way the graph names it, so a row can be pasted into a query."""
        return f"{self.module}:{self.qualname}"


@dataclass(frozen=True)
class Call:
    """
    A directed call between two symbols, whichever side observed it.
    """

    caller: Symbol
    callee: Symbol

    @property
    def pair(self) -> tuple[Symbol, Symbol]:
        """The caller and callee, for set arithmetic."""
        return (self.caller, self.callee)

    def render(self) -> str:
        """Render the call as one line, for sorting and for a report row."""
        return f"{self.caller.render()} -> {self.callee.render()}"


@dataclass(frozen=True)
class ObservedCall(Call):
    """
    A call that happened at runtime, recorded by the trace.
    """


@dataclass(frozen=True)
class InferredEdge(Call):
    """
    A CALLS edge the Indexing pipeline inferred without running anything.
    """

    confidence: str
    file: str | None = None
    line: int | None = None
    resolved: bool = True


@dataclass(frozen=True)
class UnresolvedEdge:
    """
    A CALLS edge whose target is a name nothing in the repository defines.

    It cannot be called a hit or a miss: there is no symbol on the other side
    for a trace to observe. The target is kept as the graph wrote it, because
    the unresolvable id is the interesting part.
    """

    caller: str
    target: str
    file: str | None = None
    line: int | None = None

    def render(self) -> str:
        """Render the edge as one line, for sorting and for a report row."""
        return f"{self.caller} -> {self.target}"


def symbol_key(node_id: str) -> Symbol | None:
    """
    Reduce a Python symbol id to the symbol a trace records.

    `python://pkg.mod:Class.method` and `python://pkg.mod.helper` both name one
    symbol. `python://helper` names something the Indexing pipeline could not
    resolve, so it matches nothing and is reported as unresolved instead.
    """
    if not node_id.startswith(SCHEME):
        return None
    body = node_id[len(SCHEME) :]
    if ":" in body:
        module, _, qualname = body.partition(":")
    else:
        module, _, qualname = body.rpartition(".")
    if not module or not qualname:
        return None
    return Symbol(module=module, qualname=qualname)


@dataclass(frozen=True)
class Comparison:
    """
    One measured run: what the trace saw, what the graph inferred, and how much
    of each lines up.
    """

    repository: str
    commit: str
    test_command: str
    observed_total: int = 0
    matched: tuple[tuple[ObservedCall, InferredEdge], ...] = ()
    unmatched_observed: tuple[ObservedCall, ...] = ()
    unobserved_inferred: tuple[InferredEdge, ...] = ()
    unresolved_edges: tuple[UnresolvedEdge, ...] = ()
    inferred_total: int = 0
    failure: str | None = None
    missed_from_unresolved: int = 0
    missed_to_override: int = 0
    missed_from_silent: int = 0

    @property
    def matched_count(self) -> int:
        """How many observed calls the graph also holds."""
        return len(self.matched)

    @property
    def unresolved_count(self) -> int:
        """How many inferred edges name a target the trace cannot judge."""
        return len(self.unresolved_edges)

    @property
    def judgeable_total(self) -> int:
        """
        How many inferred edges a trace could have judged at all: every CALLS
        edge except the ones pointing at a name nothing in the repository
        defines. This, not `inferred_total`, is the denominator for "the trace
        never saw this edge".
        """
        return self.inferred_total - self.unresolved_count

    @property
    def measured(self) -> bool:
        """
        Whether this run produced a figure at all. A run that failed, and a run
        that observed no calls, are both unmeasured.
        """
        return self.failure is None and self.observed_total > 0

    @property
    def precision(self) -> float | None:
        """
        The share of observed calls that were also inferred as Edges.

        None when there is nothing to divide, which is a failure to trace
        rather than a perfect score.
        """
        if not self.measured:
            return None
        return self.matched_count / self.observed_total

    def failed(self, reason: str) -> Comparison:
        """Return the same run, marked as a failure to trace."""
        return Comparison(
            repository=self.repository,
            commit=self.commit,
            test_command=self.test_command,
            failure=reason,
        )


def _defined_symbols(graph: GraphStore) -> set[Symbol]:
    """
    Every symbol the graph holds a definition for, that is, every node that
    came out of a file.

    An edge to `python://pkg.mod.helper` and the definition node
    `python://pkg.mod:helper` are the same symbol under two id conventions, so
    a definition is looked up by reduced key rather than by id.
    """
    keys: set[Symbol] = set()
    for node in graph.nodes.values():
        if node.file is None:
            continue
        key = symbol_key(node.id)
        if key is not None:
            keys.add(key)
    return keys


@dataclass(frozen=True)
class InferredCalls:
    """
    The graph's CALLS edges, split by whether a trace can judge them.
    """

    edges: list[InferredEdge]
    unresolved: list[UnresolvedEdge]
    total: int
    unresolved_only_callers: set[Symbol]
    declared_by_caller: dict[Symbol, dict[str, set[str]]]

    @property
    def judgeable(self) -> list[InferredEdge]:
        """The edges whose target is a symbol the repository defines."""
        return [edge for edge in self.edges if edge.resolved]

    def dispatched_elsewhere(self, call: ObservedCall) -> bool:
        """
        Whether the pipeline named a method of the same name on another class.

        A call through `self` resolves statically to the method the class
        declares and lands at runtime on whatever subclass answered it. Both
        readings are correct and they are not the same edge, so the mismatch is
        a fact about dynamic dispatch rather than a mistake in either side. It
        is named so that a reader can tell it apart from a genuine miss.
        """
        declared = self.declared_by_caller.get(call.caller, {})
        name = call.callee.qualname.rsplit(".", 1)[-1]
        targets = declared.get(name)
        if not targets:
            return False
        return call.callee.qualname not in targets


def _inferred_calls(graph: GraphStore, defined: set[Symbol]) -> InferredCalls:
    """
    Read every CALLS edge, keeping the ones a trace can judge apart.

    A caller all of whose edges are unresolvable is tracked separately, because
    "the pipeline saw the call and could not name it" and "the pipeline never
    saw the call" are different defects and a reader should be able to tell
    them apart.
    """
    edges: list[InferredEdge] = []
    unresolved: list[UnresolvedEdge] = []
    resolved_by_caller: dict[Symbol | str, bool] = {}
    declared_by_caller: dict[Symbol, dict[str, set[str]]] = {}
    total = 0
    for edge in graph.get_edges_by_type("CALLS"):
        total += 1
        caller = symbol_key(edge.source)
        callee = symbol_key(edge.target)
        key = caller if caller is not None else edge.source
        resolved = caller is not None and callee is not None and callee in defined
        resolved_by_caller[key] = resolved_by_caller.get(key) or resolved

        if caller is not None and callee is not None:
            edges.append(
                InferredEdge(
                    caller=caller,
                    callee=callee,
                    confidence=edge.confidence,
                    file=edge.file,
                    line=edge.line,
                    resolved=callee in defined,
                )
            )
            if callee in defined:
                name = callee.qualname.rsplit(".", 1)[-1]
                targets = declared_by_caller.setdefault(caller, {}).setdefault(
                    name, set()
                )
                targets.add(callee.qualname)
        if not resolved:
            unresolved.append(
                UnresolvedEdge(
                    caller=edge.source,
                    target=edge.target,
                    file=edge.file,
                    line=edge.line,
                )
            )
    return InferredCalls(
        edges=edges,
        unresolved=unresolved,
        total=total,
        unresolved_only_callers={
            key
            for key, any_resolved in resolved_by_caller.items()
            if isinstance(key, Symbol) and not any_resolved
        },
        declared_by_caller=declared_by_caller,
    )


def compare(
    *,
    repository: str,
    commit: str,
    test_command: str,
    observed: Iterable[ObservedCall],
    graph: GraphStore,
) -> Comparison:
    """
    Diff the calls that happened against the Edges that were inferred.
    """
    observed_calls = list(observed)
    inferred = _inferred_calls(graph, _defined_symbols(graph))
    by_pair = {edge.pair: edge for edge in inferred.edges}
    seen = {call.pair for call in observed_calls}

    matched: list[tuple[ObservedCall, InferredEdge]] = []
    unmatched: list[ObservedCall] = []
    for call in sorted(observed_calls, key=lambda c: c.render()):
        edge = by_pair.get(call.pair)
        if edge is None:
            unmatched.append(call)
        else:
            matched.append((call, edge))

    unobserved = [
        edge
        for edge in sorted(inferred.judgeable, key=lambda e: e.render())
        if edge.pair not in seen
    ]
    from_unresolved = sum(
        1 for call in unmatched if call.caller in inferred.unresolved_only_callers
    )
    dispatched = [call for call in unmatched if inferred.dispatched_elsewhere(call)]
    remaining = len(unmatched) - from_unresolved - len(dispatched)
    return Comparison(
        repository=repository,
        commit=commit,
        test_command=test_command,
        observed_total=len(observed_calls),
        matched=tuple(matched),
        unmatched_observed=tuple(unmatched),
        unobserved_inferred=tuple(unobserved),
        unresolved_edges=tuple(sorted(inferred.unresolved, key=lambda e: e.render())),
        inferred_total=inferred.total,
        missed_from_unresolved=from_unresolved,
        missed_to_override=len(dispatched),
        missed_from_silent=remaining,
    )
