"""Contract tests for the MCP tools the README advertises.

The tool list is the surface a reader is invited to try, so every tool named in
the documentation is called here with real arguments against a real Graph and its
response is held to the envelope the rest of the suite and the generated demo
rely on: `ok`, `data` or `error`, and `meta`. Errors are asserted on their code
and their message, never on the exception that produced them.

The Graph fixtures come from `conftest.py` and from a repository indexed for
real, so nothing here duplicates a graph the suite already has.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from saurix.agents.mcp import handlers
from saurix.agents.mcp.server import create_server
from saurix.core.config import config
from saurix.core.graph import GraphStore


@dataclass(frozen=True)
class QueryTool:
    """
    One query tool and everything the suite asserts about it.

    The rows it promises, a valid argument set that finds something in the
    fixture Graph, the discovery query it delegates to, and the code it reports
    when that query fails. One record per tool, so adding a tool is one edit.
    """

    name: str
    handler: Callable[..., dict]
    arguments: dict[str, Any]
    row_keys: set[str]
    query: str
    failure_code: str


# The tools that read a Graph and answer with rows. The fixture graph holds
# `func1` calling `func2`, with `func1` imported from `module2`, so every
# argument set below has something real to return.
QUERY_TOOLS = [
    QueryTool(
        name="find_symbol",
        handler=handlers.find,
        arguments={"query": "func"},
        row_keys={"id", "type", "name", "file"},
        query="find_symbol",
        failure_code="FIND_FAILED",
    ),
    QueryTool(
        name="callers",
        handler=handlers.callers,
        arguments={"symbol": "func1"},
        row_keys={"caller", "caller_name", "line", "confidence"},
        query="callers_of",
        failure_code="CALLERS_FAILED",
    ),
    QueryTool(
        name="callees",
        handler=handlers.callees,
        arguments={"symbol": "func1"},
        row_keys={"callee", "callee_name", "line", "confidence"},
        query="callees_of",
        failure_code="CALLEES_FAILED",
    ),
    QueryTool(
        name="path_between",
        handler=handlers.path_between,
        arguments={
            "source": "python://module2:Class1.method1",
            "target": "func2",
        },
        row_keys={"step", "edge", "id", "type", "name", "file"},
        query="shortest_path",
        failure_code="PATH_FAILED",
    ),
    QueryTool(
        name="impact_of_symbol",
        handler=handlers.impact,
        arguments={"symbol": "func2"},
        row_keys={"distance", "via", "id", "type", "name", "file"},
        query="impact_of",
        failure_code="IMPACT_FAILED",
    ),
    QueryTool(
        name="related_files",
        handler=handlers.related,
        arguments={"file": "module1.py"},
        row_keys=set(),
        query="related_files",
        failure_code="RELATED_FAILED",
    ),
]

# The tools that read a Graph but answer with something other than rows.
WHOLE_GRAPH_TOOLS = {"index_repo": handlers.index_repo, "stats": handlers.stats}

# Every tool the server registers, which is every tool the README names.
ADVERTISED_TOOLS = {tool.name: tool.handler for tool in QUERY_TOOLS} | (
    WHOLE_GRAPH_TOOLS
)


def call_tool(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """
    Call a tool on a real server instance and return its parsed response.
    """
    result = asyncio.run(create_server().call_tool(tool, arguments))
    return json.loads(result[0].text)


# The handlers module, as a file to read for the codes it can return.
HANDLERS = Path(handlers.__file__).parent

# The README shouts in backticks for other reasons too; the Edge types are not
# failure codes.
EDGE_TYPES = {"CONTAINS", "CALLS", "IMPORTS", "INHERITS"}

# The query tools that answer with rows; `related_files` answers with paths.
ROW_TOOLS = [tool for tool in QUERY_TOOLS if tool.row_keys]


def assert_envelope(response: dict[str, Any]) -> None:
    """
    Assert the envelope every tool shares, whether it succeeded or not.

    Successes carry `data`, failures carry `error`, never both and never
    neither, and both are timed.
    """
    assert set(response) <= {"ok", "data", "error", "meta"}
    assert isinstance(response["ok"], bool)
    assert ("data" in response) != ("error" in response)
    assert isinstance(response["meta"]["duration_ms"], int)
    assert response["meta"]["duration_ms"] >= 0


@pytest.fixture
def indexed_graph(temp_repo: Path, tmp_path: Path) -> str:
    """
    Index the sample repository and return the path of the Graph it produced.
    """
    out = tmp_path / "indexed.graph.json"
    response = handlers.index_repo(source=str(temp_repo), out=str(out))
    assert response["ok"], response
    return str(out)


@pytest.fixture
def broken_graph(tmp_path: Path) -> str:
    """
    Return the path of a file that is not a Graph at all.
    """
    path = tmp_path / "broken.graph.json"
    path.write_text("{ this is not json")
    return str(path)


class TestDocumentedSurface:
    """
    The tools the documentation names are the tools the server registers.
    """

    def test_readme_names_every_registered_tool(self) -> None:
        """
        Every tool in the advertised set is named by hand in the README.
        """
        readme = (Path(__file__).resolve().parent.parent / "README.md").read_text()
        missing = sorted(tool for tool in ADVERTISED_TOOLS if f"`{tool}`" not in readme)
        assert not missing, f"the README never names {missing}"

    def test_server_registers_the_advertised_tools(self) -> None:
        """
        The registered tool list is the advertised one, no more and no less.
        """
        registered = {tool.name for tool in asyncio.run(create_server().list_tools())}
        assert registered == set(ADVERTISED_TOOLS)

    def test_readme_documents_every_failure_code(self) -> None:
        """
        Every code the handlers can return is named in the README, and every code
        the README names is one the handlers can return.
        """
        source = (HANDLERS / "handlers.py").read_text()
        returned = set(re.findall(r'"([A-Z][A-Z_]+)"', source))
        readme = (HANDLERS.parents[2] / "README.md").read_text()
        documented = set(re.findall(r"`([A-Z][A-Z_]+)`", readme)) - EDGE_TYPES
        assert returned == documented


class TestQueryTools:
    """
    Every query tool answers with the rows and the metadata it promises.
    """

    @pytest.mark.parametrize("tool", ROW_TOOLS, ids=lambda t: t.name)
    def test_query_tool_returns_rows(
        self, tool: QueryTool, temp_graph_file: Path
    ) -> None:
        """
        A query tool returns rows carrying its documented keys, and counts them.
        """
        response = call_tool(
            tool.name, {"graph": str(temp_graph_file), **tool.arguments}
        )
        assert_envelope(response)
        assert response["ok"] is True
        assert response["data"], f"{tool.name} found nothing in the fixture graph"
        for row in response["data"]:
            assert set(row) == tool.row_keys
        assert response["meta"]["count"] == len(response["data"])

    @pytest.mark.parametrize("tool", QUERY_TOOLS, ids=lambda t: t.name)
    def test_query_tool_runs_on_an_indexed_graph(
        self, tool: QueryTool, indexed_graph: str
    ) -> None:
        """
        The same contract holds against a Graph produced by real indexing.
        """
        response = call_tool(tool.name, {"graph": indexed_graph, **tool.arguments})
        assert_envelope(response)
        assert response["ok"] is True
        assert isinstance(response["data"], list)
        assert response["meta"]["count"] == len(response["data"])


class TestIndexRepo:
    """
    The indexing tool reports what it indexed, where it wrote the Graph, and
    what it found there.
    """

    def test_indexes_a_repository(self, temp_repo: Path, tmp_path: Path) -> None:
        """
        Indexing a local checkout writes a Graph and reports the counts.
        """
        out = tmp_path / "written.graph.json"
        response = call_tool("index_repo", {"source": str(temp_repo), "out": str(out)})
        assert_envelope(response)
        assert response["ok"] is True
        data = response["data"]
        assert set(data) == {
            "graph_path",
            "source_kind",
            "scanned_files",
            "indexed_files",
            "stats",
        }
        assert data["graph_path"] == str(out)
        assert data["source_kind"] == "local"
        assert data["indexed_files"] >= 1
        assert data["stats"]["nodes"] >= 1
        assert out.exists()

    def test_reports_a_source_that_does_not_exist(self, tmp_path: Path) -> None:
        """
        A source that is neither a path nor a GitHub URL is named in the error.
        """
        missing = tmp_path / "nowhere"
        response = call_tool("index_repo", {"source": str(missing)})
        assert_envelope(response)
        assert response["ok"] is False
        assert response["error"]["code"] == "INVALID_SOURCE"
        assert str(missing) in response["error"]["message"]

    @pytest.mark.parametrize(
        ("code", "failure"),
        [
            ("SOURCE_NOT_FOUND", FileNotFoundError("module1.py")),
            ("PERMISSION_DENIED", PermissionError("module1.py")),
            ("INDEX_FAILED", RuntimeError("grammar missing")),
        ],
    )
    def test_indexing_failure_is_reported(
        self, code: str, failure: Exception, temp_repo: Path, monkeypatch
    ) -> None:
        """
        Whatever goes wrong while indexing comes back as an error, not a trace.
        """

        def explode(*args: Any, **kwargs: Any) -> None:
            """
            Stand in for indexing that fails on a repository it cannot read.
            """
            raise failure

        monkeypatch.setattr(handlers, "build_graph", explode)
        response = call_tool("index_repo", {"source": str(temp_repo)})
        assert_envelope(response)
        assert response["ok"] is False
        assert response["error"]["code"] == code
        assert str(failure) in response["error"]["message"]


class TestGraphThatIsNotAGraph:
    """
    Valid JSON is not enough: the payload has to be a Saurix graph.
    """

    def test_reports_a_payload_the_loader_cannot_read(
        self, tmp_path: Path, temp_graph_file: Path
    ) -> None:
        """
        A JSON file whose nodes carry unknown fields is reported, not raised.
        """
        path = tmp_path / "wrong-shape.graph.json"
        path.write_text(json.dumps({"schema_version": "1.0.0", "nodes": [{"x": 1}]}))
        response = call_tool("find_symbol", {"graph": str(path), "query": "func"})
        assert_envelope(response)
        assert response["ok"] is False
        assert response["error"]["code"] == "INVALID_GRAPH"
        assert str(path) in response["error"]["message"]


class TestStats:
    """
    The stats tool summarises the Graph it is pointed at.
    """

    def test_reports_graph_totals(self, temp_graph_file: Path) -> None:
        """
        Stats carry the totals and the histograms a reader expects.
        """
        response = call_tool("stats", {"graph": str(temp_graph_file)})
        assert_envelope(response)
        assert response["ok"] is True
        assert {
            "nodes",
            "edges",
            "node_types",
            "edge_types",
            "languages",
            "confidence_counts",
            "confidence_percentages",
        } <= set(response["data"])
        assert response["data"]["nodes"] == 6
        assert response["data"]["edges"] == 7

    def test_reports_a_stats_failure(
        self, temp_graph_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        Stats that cannot be computed come back as STATS_FAILED.
        """

        def explode(self: Any) -> dict[str, Any]:
            """
            Stand in for a graph whose totals cannot be worked out.
            """
            raise RuntimeError("stats exploded")

        monkeypatch.setattr(GraphStore, "stats", explode)
        response = call_tool("stats", {"graph": str(temp_graph_file)})
        assert_envelope(response)
        assert response["ok"] is False
        assert response["error"]["code"] == "STATS_FAILED"
        assert "stats exploded" in response["error"]["message"]


class TestGraphFailures:
    """
    A Graph that cannot be read fails with a code and a path the caller can use.
    """

    @pytest.mark.parametrize("tool", sorted(set(ADVERTISED_TOOLS) - {"index_repo"}))
    @pytest.mark.parametrize("kind", ["absent", "malformed", "unreadable"])
    def test_unreadable_graph_is_reported(
        self,
        tool: str,
        kind: str,
        temp_graph_file: Path,
        broken_graph: str,
    ) -> None:
        """
        Absent, malformed, and unreadable Graph paths each get their own code.
        """
        graph = {
            "absent": str(temp_graph_file.parent / "absent.graph.json"),
            "malformed": broken_graph,
            "unreadable": str(temp_graph_file.parent),
        }[kind]
        arguments = _arguments(tool)
        response = call_tool(tool, {"graph": graph, **arguments})
        assert_envelope(response)
        assert response["ok"] is False
        assert (
            response["error"]["code"]
            == {
                "absent": "GRAPH_NOT_FOUND",
                "malformed": "INVALID_GRAPH",
                "unreadable": "GRAPH_UNREADABLE",
            }[kind]
        )
        assert graph in response["error"]["message"]


class TestUnresolvableArguments:
    """
    A symbol or file the Graph does not hold is named back, not raised.
    """

    @pytest.mark.parametrize(
        "tool", ["callers", "callees", "impact_of_symbol"], ids=lambda t: t
    )
    def test_unknown_symbol(self, tool: str, temp_graph_file: Path) -> None:
        """
        Asking about a symbol the graph never saw returns SYMBOL_NOT_FOUND.
        """
        response = call_tool(
            tool,
            {
                "graph": str(temp_graph_file),
                **_arguments(tool),
                "symbol": "ghost_symbol",
            },
        )
        assert_envelope(response)
        assert response["ok"] is False
        assert response["error"]["code"] == "SYMBOL_NOT_FOUND"
        assert "ghost_symbol" in response["error"]["message"]

    @pytest.mark.parametrize("endpoint", ["source", "target"])
    def test_unresolvable_path_endpoint(
        self, endpoint: str, temp_graph_file: Path
    ) -> None:
        """
        Either end of a path that resolves to nothing is reported by name.
        """
        response = call_tool(
            "path_between",
            {
                "graph": str(temp_graph_file),
                **_arguments("path_between"),
                endpoint: "ghost",
            },
        )
        assert_envelope(response)
        assert response["ok"] is False
        assert response["error"]["code"] == "SYMBOL_NOT_FOUND"
        assert "ghost" in response["error"]["message"]

    def test_path_between_known_symbols_with_no_route(
        self, temp_graph_file: Path
    ) -> None:
        """
        A pair the graph knows but does not connect is an empty result: both ends
        resolved, so nothing went wrong.
        """
        response = call_tool(
            "path_between",
            {
                "graph": str(temp_graph_file),
                "source": "python://module1:func1",
                "target": "python://module2:Class1",
            },
        )
        assert_envelope(response)
        assert response["ok"] is True
        assert response["data"] == []
        assert response["meta"]["count"] == 0

    def test_unknown_file(self, temp_graph_file: Path) -> None:
        """
        A file path absent from the graph is reported with its own code.
        """
        response = call_tool(
            "related_files", {"graph": str(temp_graph_file), "file": "ghost.py"}
        )
        assert_envelope(response)
        assert response["ok"] is False
        assert response["error"]["code"] == "FILE_NOT_FOUND"
        assert "ghost.py" in response["error"]["message"]

    def test_query_that_matches_nothing_is_an_empty_result(
        self, temp_graph_file: Path
    ) -> None:
        """
        A fuzzy query is a question, not a lookup: no match means no rows, not
        an error. Only a tool asked about a specific symbol reports a miss.
        """
        response = call_tool(
            "find_symbol", {"graph": str(temp_graph_file), "query": "ghost_symbol"}
        )
        assert_envelope(response)
        assert response["ok"] is True
        assert response["data"] == []
        assert response["meta"]["count"] == 0


class TestArgumentBounds:
    """
    Result-size and depth arguments are clamped, not obeyed literally.
    """

    def test_limit_is_clamped_to_at_least_one(self, temp_graph_file: Path) -> None:
        """
        A limit of zero still returns one row, never an error.
        """
        response = call_tool(
            "callers",
            {"graph": str(temp_graph_file), "symbol": "func1", "limit": 0},
        )
        assert_envelope(response)
        assert response["ok"] is True
        assert response["meta"]["count"] == 1

    def test_limit_is_clamped_to_the_configured_maximum(
        self, temp_graph_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        A limit past the configured maximum returns that maximum, not more.

        The cap is lowered so the assertion bites: with the shipped maximum the
        fixture Graph is smaller than the cap, and any value would pass.
        """
        monkeypatch.setattr(config, "max_limit", 2)
        response = call_tool(
            "find_symbol",
            {"graph": str(temp_graph_file), "query": "python", "limit": 10_000},
        )
        assert_envelope(response)
        assert response["ok"] is True
        assert response["meta"]["count"] == 2

    def test_depth_walks_exactly_as_far_as_it_is_told(
        self, temp_graph_file: Path
    ) -> None:
        """
        The depth argument decides how far the walk reaches: one hop finds the
        single caller of `func1`, three finds its callers and their callers.
        """
        counts = {depth: _impact_count(temp_graph_file, depth) for depth in (1, 3)}
        assert counts[1] == 2, "one hop reaches the caller and the module"
        assert counts[3] > counts[1]

    @pytest.mark.parametrize("depth", [-5, 0])
    def test_depth_below_one_walks_one_hop(
        self, depth: int, temp_graph_file: Path
    ) -> None:
        """
        A depth of zero or less is clamped up to one hop, not down to nothing.
        """
        assert _impact_count(temp_graph_file, depth) == 2

    def test_depth_is_clamped_to_the_configured_maximum(
        self, temp_graph_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        A depth past the configured maximum walks no further than the maximum.
        """
        monkeypatch.setattr(config, "max_depth", 1)
        response = call_tool(
            "impact_of_symbol",
            {
                "graph": str(temp_graph_file),
                "symbol": "func1",
                "depth": 10_000,
                "limit": 50,
            },
        )
        assert_envelope(response)
        assert response["ok"] is True
        assert response["meta"]["count"] == 2

    def test_blank_symbol_is_reported(self, temp_graph_file: Path) -> None:
        """
        An empty symbol name is a missing symbol, reported like any other.
        """
        response = call_tool("callers", {"graph": str(temp_graph_file), "symbol": ""})
        assert response["ok"] is False
        assert response["error"]["code"] == "SYMBOL_NOT_FOUND"


class TestQueryFailureReporting:
    """
    A query that blows up is reported under the code of the tool that ran it.
    """

    @pytest.mark.parametrize("tool", QUERY_TOOLS, ids=lambda t: t.name)
    def test_query_failure_is_wrapped(
        self,
        tool: QueryTool,
        temp_graph_file: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Each query handler reports its own failure code and keeps the message.
        """

        def explode(*args: Any, **kwargs: Any) -> list[dict[str, str]]:
            """
            Stand in for a query layer that fails unexpectedly.
            """
            raise RuntimeError("query layer exploded")

        monkeypatch.setattr(handlers, tool.query, explode)
        response = call_tool(
            tool.name, {"graph": str(temp_graph_file), **tool.arguments}
        )
        assert_envelope(response)
        assert response["ok"] is False
        assert response["error"]["code"] == tool.failure_code
        assert "query layer exploded" in response["error"]["message"]


def _arguments(tool: str) -> dict[str, Any]:
    """
    Return the valid arguments of a tool, the graph argument left out.
    """
    return next((case.arguments for case in QUERY_TOOLS if case.name == tool), {})


def _impact_count(graph: Path, depth: int) -> int:
    """
    Return how many symbols the blast radius of `func1` reaches at a depth.
    """
    response = call_tool(
        "impact_of_symbol",
        {"graph": str(graph), "symbol": "func1", "depth": depth, "limit": 50},
    )
    assert_envelope(response)
    assert response["ok"] is True
    return response["meta"]["count"]
