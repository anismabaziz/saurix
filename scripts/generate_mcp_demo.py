"""
Documentation Generator

Drives the real MCP server against a real repository and writes the two
documents that are easy to get wrong by hand: the tool-call demo and the
agent-lifecycle walkthrough. Every identifier in them comes back from a live
response, so a reader who copies a call gets a working call.

Timings and absolute paths are stripped from the captured payloads, which makes
the output a pure function of the indexed code. That is what lets `--check` tell
rot apart from noise. The graph is built from the working tree, so uncommitted
source edits show up in the output; CI checks out a clean tree and expects the
committed documents to match what a clean run produces.

Usage:
    uv run scripts/generate_mcp_demo.py
    uv run scripts/generate_mcp_demo.py --check
    uv run scripts/generate_mcp_demo.py --source ../some/other/repo
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from saurix.agents.mcp.server import create_server

Predicate = Callable[[dict[str, Any]], bool]

REPO_ROOT = Path(__file__).resolve().parent.parent

# The demo follows indexing end to end: the graph-building entry point that the
# CLI and the MCP server both reach for.
DEMO_QUERY = "build_graph"
CALL_TARGET = "core.indexing.build_graph"

GRAPH_ARG = "tmp/saurix.demo.graph.json"

DEMO_PATH = "demo-mcp.md"
LIFECYCLE_PATH = "docs/agent-lifecycle.md"

PROVENANCE_START = "<!-- provenance -->"
PROVENANCE_END = "<!-- /provenance -->"


class DemoError(RuntimeError):
    """
    Raised when a call the documents promise does not behave as promised.
    """


@dataclass(frozen=True)
class Call:
    """
    One MCP tool call together with the response it actually produced.
    """

    title: str
    tool: str
    arguments: dict[str, Any]
    response: dict[str, Any]
    takeaway: str

    def argument_block(self) -> str:
        """
        Render the call as an MCP tool invocation.
        """
        return json.dumps({"tool": self.tool, "arguments": self.arguments}, indent=2)

    def response_block(self) -> str:
        """
        Render the captured response as JSON.
        """
        return json.dumps(self.response, indent=2)


@dataclass
class Transcript:
    """
    Everything one run learned, kept in the shape the two documents need.
    """

    calls: list[Call] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    definition: dict[str, Any] = field(default_factory=dict)
    callers: list[dict[str, Any]] = field(default_factory=list)
    caller: dict[str, Any] = field(default_factory=dict)
    path: list[dict[str, Any]] = field(default_factory=list)
    blast_radius: list[dict[str, Any]] = field(default_factory=list)
    related: list[str] = field(default_factory=list)

    def call(self, tool: str) -> Call:
        """
        Return the recorded call for a tool.
        """
        for call in self.calls:
            if call.tool == tool:
                return call
        raise DemoError(f"no recorded call for tool {tool}")


def _git(source: Path, *args: str) -> str:
    """
    Run a read-only git command in a checkout, returning `unknown` on failure.
    """
    try:
        return subprocess.run(
            ["git", *args],
            cwd=source,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover
        return "unknown"


def resolve_source(source: str) -> Path:
    """
    Resolve a `--source` argument to an absolute directory.
    """
    root = Path(source)
    return (root if root.is_absolute() else REPO_ROOT / root).resolve()


def repo_identity(source: str) -> tuple[str, str]:
    """
    Name the repository a document was generated against, and at which commit.

    The slug comes from the checkout's own remote, so documenting a different
    repository does not stamp this project's name on it.
    """
    root = resolve_source(source)
    remote = _git(root, "config", "--get", "remote.origin.url")
    if remote == "unknown":
        slug = root.name
    else:
        # Owner and repo, whichever of the SSH and HTTPS forms the remote uses.
        parts = re.split(r"[:/]", remote.removesuffix(".git"))
        slug = "/".join(parts[-2:]) if len(parts) > 1 else parts[-1]
    return slug, _git(root, "rev-parse", "HEAD")


def _stable(value: Any, root: Path) -> Any:
    """
    Recursively drop timings and de-absolutise paths.

    Wall-clock durations and absolute paths differ on every run and on every
    machine; the information a reader needs is everything else.
    """
    if isinstance(value, dict):
        return {
            key: _stable(item, root)
            for key, item in value.items()
            if key != "duration_ms"
        }
    if isinstance(value, list):
        return [_stable(item, root) for item in value]
    if isinstance(value, str):
        return value.replace(f"{root}/", "")
    return value


def _invoke(
    app: Any, tool: str, arguments: dict[str, Any], root: Path
) -> dict[str, Any]:
    """
    Call one tool on the live server and return its parsed response.
    """
    result = asyncio.run(app.call_tool(tool, arguments))
    text = result[0].text if result else ""
    try:
        payload = _stable(json.loads(text), root)
    except json.JSONDecodeError as exc:  # pragma: no cover
        raise DemoError(f"{tool} returned a non-JSON payload: {text!r}") from exc
    # Some responses carry nothing in `meta` once timings are gone.
    if isinstance(payload, dict) and not payload.get("meta"):
        payload.pop("meta")
    return payload


def _require(response: dict[str, Any], tool: str) -> dict[str, Any]:
    """
    Assert a documented call succeeded, with a message worth reading on failure.
    """
    if not response.get("ok"):
        raise DemoError(f"{tool} failed during documentation generation: {response}")
    return response


def _rows(response: dict[str, Any], tool: str) -> list[dict[str, Any]]:
    """
    Return the result rows of a query call, refusing to document an empty one.
    """
    rows = _require(response, tool).get("data") or []
    if not rows:
        raise DemoError(
            f"{tool} returned no rows; the demo would document an empty result"
        )
    return rows


def _pick(
    rows: list[dict[str, Any]], label: str, predicate: Predicate
) -> dict[str, Any]:
    """
    Return the first row satisfying a predicate, or explain what was on offer.
    """
    for row in rows:
        if predicate(row):
            return row
    seen = ", ".join(sorted({str(row.get("name")) for row in rows}))
    raise DemoError(f"no {label} in the response; saw: {seen}")


def run_scenario(source: str, graph_arg: str) -> Transcript:
    """
    Run the documented workflow end to end and record every response.

    The steps are deliberately chained: each one feeds the next symbol id back
    in, so the document stays truthful even after a refactor renames things.
    """
    app = create_server()
    root = resolve_source(source)
    transcript = Transcript()

    def record(
        title: str, tool: str, arguments: dict[str, Any], takeaway: str
    ) -> dict[str, Any]:
        response = _require(_invoke(app, tool, arguments, root), tool)
        transcript.calls.append(Call(title, tool, arguments, response, takeaway))
        return response

    record(
        "Index a repository",
        "index_repo",
        {"source": source, "out": graph_arg},
        f"Scans the checkout, dispatches every file to an extractor, and writes "
        f"the graph to `{graph_arg}`. Every later call reads that file.",
    )

    graph_args = {"graph": graph_arg}
    transcript.stats = record(
        "Read the graph stats",
        "stats",
        graph_args,
        "Node, edge, language and confidence totals, plus how much of the "
        "repository the extractors actually covered.",
    )["data"]

    matches = _rows(
        record(
            "Find a symbol by name",
            "find_symbol",
            {**graph_args, "query": DEMO_QUERY, "limit": 10},
            "Fuzzy search across definitions and references. The first row is the "
            "definition; the rest are the reference sites other files resolve to.",
        ),
        "find_symbol",
    )
    # The definition is the row that knows its own file; the reference is the id
    # that call sites elsewhere in the graph point at.
    transcript.definition = _pick(matches, "definition", lambda row: bool(row["file"]))
    call_target = _pick(
        matches,
        f"reference to `{DEMO_QUERY}`",
        lambda row: row["name"] == CALL_TARGET,
    )

    transcript.callers = _rows(
        record(
            "List the callers of a symbol",
            "callers",
            {**graph_args, "symbol": call_target["name"], "limit": 10},
            "Reverse `CALLS` edges: who reaches this symbol, and on which line.",
        ),
        "callers",
    )
    transcript.caller = transcript.callers[-1]
    caller_id = transcript.caller["caller"]

    _rows(
        record(
            "List the callees of a symbol",
            "callees",
            {**graph_args, "symbol": caller_id, "limit": 10},
            "Outgoing `CALLS` edges: the functions one function reaches, with the "
            "line of each call site.",
        ),
        "callees",
    )

    transcript.path = _rows(
        record(
            "Find the path between two symbols",
            "path_between",
            {
                **graph_args,
                "source": caller_id,
                "target": call_target["id"],
                "max_depth": 12,
            },
            "The shortest directed walk joining them, one row per step.",
        ),
        "path_between",
    )

    transcript.blast_radius = _rows(
        record(
            "Measure the blast radius of a change",
            "impact_of_symbol",
            {**graph_args, "symbol": call_target["id"], "depth": 3, "limit": 50},
            "Everything within three hops upstream of the symbol, with the edge "
            "that reaches it and how far away it is.",
        ),
        "impact_of_symbol",
    )

    transcript.related = _rows(
        record(
            "List the files related to a file",
            "related_files",
            {
                **graph_args,
                "file": transcript.definition["file"],
                "depth": 2,
                "limit": 10,
            },
            "Neighbour files of a file path, ranked by how tightly the graph ties "
            "them to it.",
        ),
        "related_files",
    )
    return transcript


def provenance(source: str) -> str:
    """
    Build the header block that tells a reader how old the document is.
    """
    slug, commit = repo_identity(source)
    return "\n".join(
        [
            PROVENANCE_START,
            f"- Indexed repository: `{slug}` (source `{source}`)",
            f"- Indexed commit: `{commit}`",
            PROVENANCE_END,
        ]
    )


def strip_provenance(text: str) -> str:
    """
    Drop the provenance block, leaving the part a change to the code can move.

    The commit moves on every commit, so comparing it would report rot where
    there is none.
    """
    lines = text.splitlines()
    kept: list[str] = []
    inside = False
    for line in lines:
        if line.strip() == PROVENANCE_START:
            inside = True
            continue
        if line.strip() == PROVENANCE_END:
            inside = False
            continue
        if not inside:
            kept.append(line)
    return "\n".join(kept).strip() + "\n"


def _code(payload: str) -> str:
    """
    Wrap a block of JSON in a fenced code block.
    """
    return f"```json\n{payload}\n```"


def render_demo(transcript: Transcript, source: str) -> str:
    """
    Render the tool-call demo from a recorded transcript.
    """
    sections = [
        "# MCP Demo (Saurix)",
        "",
        "Generated by `scripts/generate_mcp_demo.py`. Every call below was "
        "executed against a real repository and every response is the real "
        "response, minus the `duration_ms` fields, which change on every run.",
        "",
        provenance(source),
        "",
        "Refresh it with:",
        "",
        "```sh",
        "uv run scripts/generate_mcp_demo.py",
        "```",
        "",
        "## Prerequisites",
        "",
        "- Run `uv sync`.",
        "- Start the server with `saurix-mcp`, then send the calls below.",
        f"- `source` is `{source}` here because the run was made against a local "
        f"checkout. The tool takes a GitHub URL just as happily.",
        "",
    ]
    for number, call in enumerate(transcript.calls, start=1):
        sections += [
            f"## {number}. {call.title}",
            "",
            "Tool call:",
            "",
            _code(call.argument_block()),
            "",
            "Response:",
            "",
            _code(call.response_block()),
            "",
            call.takeaway,
            "",
        ]
    return "\n".join(sections).rstrip() + "\n"


def _chain(path: list[dict[str, Any]]) -> str:
    """
    Render a path result as a readable arrow chain.
    """
    parts = [f"`{row['name']}`" for row in path]
    return " -> ".join(parts)


def _join(values: list[str]) -> str:
    """
    Render a list as prose: `a`, `a` and `b`, or `a`, `b` and `c`.
    """
    quoted = [f"`{value}`" for value in values]
    if len(quoted) == 1:
        return quoted[0]
    return f"{', '.join(quoted[:-1])} and {quoted[-1]}"


def _count(quantity: int, word: str) -> str:
    """
    Render a count with its noun, pluralised only when it has to be.
    """
    if quantity == 1:
        return f"1 {word}"
    stem = f"{word}es" if word.endswith(("s", "x", "ch", "sh")) else f"{word}s"
    return f"{quantity} {stem}"


def _node_breakdown(node_types: dict[str, Any]) -> str:
    """
    Render the node type histogram as prose, largest type first.
    """
    ordered = sorted(node_types.items(), key=lambda item: (-item[1], item[0]))
    return ", ".join(_count(count, name) for name, count in ordered)


def _hop_summary(path: list[dict[str, Any]]) -> str:
    """
    Describe a path result as a number of hops spanning a number of files.
    """
    hops = max(len(path) - 1, 0)
    files = len({row["file"] for row in path if row.get("file")})
    return f"{_count(hops, 'edge')}, across {_count(files, 'file')}."


def _coverage_summary(coverage: dict[str, Any]) -> str:
    """
    Describe extractor coverage per language, or say there is none to report.
    """
    reported = [
        f"{entry['coverage_percent']}% on `{language}`"
        for language, entry in sorted(coverage.items())
        if entry.get("coverage_percent") is not None
    ]
    if not reported:
        return "The extractors reported no coverage figures."
    return f"The extractors reported coverage of {' and '.join(reported)}."


def render_lifecycle(transcript: Transcript, source: str) -> str:
    """
    Render the agent walkthrough from a recorded transcript.

    The narrative is fixed; the numbers, symbol ids and file paths in it are not.
    """
    stats = transcript.stats
    indexed = transcript.calls[0].response["data"]
    definition = transcript.definition
    caller = transcript.caller
    # `callers` rows carry no file, but the path result names the same symbol.
    caller_file = transcript.path[0].get("file")
    if not caller_file:
        raise DemoError(f"the path result names no file for {caller['caller']}")
    coverage = _coverage_summary(stats.get("extraction_coverage", {}))
    radius = len(transcript.blast_radius)
    radius_files = sorted(
        {row["file"] for row in transcript.blast_radius if row.get("file")}
    )

    return "\n".join(
        [
            "# The Lifecycle of an AI Agent using Saurix",
            "",
            "Generated by `scripts/generate_mcp_demo.py` from a real run of the "
            "MCP server. The story is the same every time; the numbers, symbol "
            "ids and file paths are whatever that repository actually produced.",
            "",
            provenance(source),
            "",
            "The task: an agent is dropped into a repository it has never seen "
            "and has to work out where indexing is wired in, before it changes "
            "anything.",
            "",
            "## Phase 1: Index and get the lay of the land",
            "",
            f"The agent indexes the checkout, then asks for `stats`. The graph "
            f"holds {_count(stats['nodes'], 'node')}, made up of "
            f"{_node_breakdown(stats['node_types'])}, joined by "
            f"{_count(stats['edges'], 'edge')}. {coverage} None of that cost "
            f"it a file read.",
            "",
            _code(transcript.call("index_repo").argument_block()),
            "",
            _code(transcript.call("stats").response_block()),
            "",
            "## Phase 2: Locate the thing it cares about",
            "",
            f"A fuzzy search for `{DEMO_QUERY}` returns the definition and the "
            f"reference sites it resolves to. The definition is "
            f"`{definition['name']}`, in `{definition['file']}`. That is the "
            f"function the rest of the work is about.",
            "",
            _code(transcript.call("find_symbol").argument_block()),
            "",
            _code(transcript.call("find_symbol").response_block()),
            "",
            "## Phase 3: Find out who depends on it",
            "",
            f"Reverse `CALLS` edges point at "
            f"{_count(len(transcript.callers), 'call site')}. "
            f"The walkthrough follows `{caller['caller_name']}`, at line "
            f"{caller['line']} of `{caller_file}`. Its callees list confirms the "
            f"edge, and a path from it to the definition returns the shortest "
            f"walk between them: {_chain(transcript.path)}.",
            "",
            _code(transcript.call("callers").argument_block()),
            "",
            _code(transcript.call("callers").response_block()),
            "",
            _code(transcript.call("callees").response_block()),
            "",
            _code(transcript.call("path_between").response_block()),
            "",
            f"{_hop_summary(transcript.path)} That is the wiring, established "
            f"before a line was written.",
            "",
            "## Phase 4: Ask what a change would break",
            "",
            f"Before touching the function, the agent asks for its blast "
            f"radius. Within three hops the change reaches {_count(radius, 'symbol')}, "
            f"across {_join(radius_files)}. Those are the places to re-read "
            f"after the edit.",
            "",
            _code(transcript.call("impact_of_symbol").argument_block()),
            "",
            _code(transcript.call("impact_of_symbol").response_block()),
            "",
            "## Phase 5: Confirm the neighbourhood",
            "",
            f"Indexing is a straight re-scan, so verification is another run. "
            f"Asking which files sit next to `{definition['file']}` shows the "
            f"neighbourhood a change there lands in: "
            f"{_join(transcript.related[:5])}.",
            "",
            _code(transcript.call("related_files").argument_block()),
            "",
            _code(transcript.call("related_files").response_block()),
            "",
            f"The whole walkthrough ran against a graph built from "
            f"{_count(indexed['scanned_files'], 'scanned file')}, of which "
            f"{indexed['indexed_files']} were indexed.",
            "",
            "## With and without Saurix",
            "",
            "| Question | Without Saurix | With Saurix |",
            "| :--- | :--- | :--- |",
            "| What is in here? | Read files until the shape appears | "
            f"`stats`, {_count(stats['nodes'], 'node')} in one call |",
            "| Where is it defined? | Grep, then read the hits | `find_symbol`, "
            f"definition at `{definition['file']}` |",
            "| What touches it? | Trace imports by hand | `callers`, "
            f"{_count(len(transcript.callers), 'call site')}; "
            f"`impact_of_symbol`, {_count(radius, 'symbol')} within three hops |",
            "| How are they connected? | Follow call sites in the editor | "
            f"`path_between`, {_chain(transcript.path)} |",
            "",
        ]
    )


def generate_docs(source: str = ".", graph_arg: str = GRAPH_ARG) -> dict[str, str]:
    """
    Generate every document the script owns, keyed by repository-relative path.
    """
    transcript = run_scenario(source, graph_arg)
    return {
        DEMO_PATH: render_demo(transcript, source),
        LIFECYCLE_PATH: render_lifecycle(transcript, source),
    }


def _stale(files: dict[str, str]) -> list[str]:
    """
    Return the paths whose committed content no longer matches a fresh run.
    """
    return [
        relative
        for relative, content in files.items()
        if not (REPO_ROOT / relative).exists()
        or strip_provenance((REPO_ROOT / relative).read_text())
        != strip_provenance(content)
    ]


def main(argv: Sequence[str] | None = None) -> int:
    """
    Write the documents, or report that they have drifted from the code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=".",
        help="repository to index and document (default: this checkout)",
    )
    parser.add_argument(
        "--graph",
        default=GRAPH_ARG,
        help=f"where to write the demo graph (default: {GRAPH_ARG})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail instead of writing when the committed documents have drifted",
    )
    args = parser.parse_args(argv)

    try:
        files = generate_docs(args.source, args.graph)
    except DemoError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.check:
        stale = _stale(files)
        if stale:
            print(
                "out of date, run `uv run scripts/generate_mcp_demo.py`:\n"
                + "\n".join(f"  {path}" for path in stale),
                file=sys.stderr,
            )
            return 1
        print(f"up to date ({len(files)} documents)")
        return 0

    for relative, content in files.items():
        (REPO_ROOT / relative).write_text(content)
        print(f"wrote {relative}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
