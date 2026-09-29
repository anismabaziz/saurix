# Saurix

[![PyPI version](https://img.shields.io/pypi/v/saurix.svg)](https://pypi.org/project/saurix/)
[![Python versions](https://img.shields.io/pypi/pyversions/saurix.svg)](https://pypi.org/project/saurix/)
[![License: MIT](https://img.shields.io/pypi/l/saurix.svg)](https://opensource.org/licenses/MIT)
[![Downloads](https://img.shields.io/pypi/dm/saurix.svg)](https://pypi.org/project/saurix/)

Saurix is an interactive knowledge graph engine that transforms complex codebases into a queryable, 2D-visualizable map. It is designed to be the **Symbolic Intelligence Layer** for modern AI coding agents.

## Why Saurix for AI Agents?

Saurix solves the "Context Window" problem for LLMs by providing a structured representation of code that is superior to keyword search:

- **Structural Awareness**: Understands `CALLS`, `INHERITS`, and `IMPORTS` relationships rather than just raw text.
- **Context Efficiency**: Agents can query specific subgraphs, receiving only the architectural context they need, drastically reducing token usage.
- **Blast Radius Analysis**: Built-in `impact` analysis allows agents to calculate the transitive side effects of a proposed change before making it.
- **Native MCP Support**: Built on the **Model Context Protocol**, allowing AI agents to treat the repository graph as an extension of their own memory.

See [docs/agent-lifecycle.md](docs/agent-lifecycle.md) for a step-by-step walkthrough of how an AI agent uses these capabilities.

---

## 1) Core Mission

- **Knowledge Extraction**: Turn local or GitHub repositories into a structured graph of symbols and relationships.
- **Agent Infrastructure**: Expose high-level tools (MCP) for autonomous agents to navigate complex architectures.
- **Fast Navigation**: Answer questions about dependencies, callers, and impact analysis in milliseconds.
- **Modular Architecture**: Built for extensibility across languages and tools.

---

## 2) Architecture

Saurix follows a clean, domain-driven modular structure designed for scale and symbolic intelligence. For a detailed breakdown of how Saurix indexes, stores, and queries code, see [docs/architecture.md](docs/architecture.md).

---

## Setup & Installation

1. **Install Saurix**:
   ```bash
   pip install saurix
   ```
2. **Initialize Any Project**:
   ```bash
   cd /path/to/your/project
   saurix init
   ```
   *This command indexes your project, creates a local 2D dashboard (`saurix.html`), and generates your MCP config in one step.*

### Running the MCP Server

Expose graph tools to AI agents (e.g., Claude Desktop, Cursor):

```bash
saurix-mcp
```

---

## 4) Interactive Commands

| Command          | Description                                           |
| ---------------- | ----------------------------------------------------- |
| `init`           | Zero-config setup for the current project             |
| `index <source>` | Index a local path or GitHub URL                      |
| `stats`          | Show graph statistics and extraction coverage         |
| `find <query>`   | Fuzzy search symbols by name or ID                    |
| `callers <sym>`  | List symbols calling the target                       |
| `path <A> <B>`   | Find shortest directed path between two symbols       |
| `impact <sym>`   | Estimate blast radius of a change                     |
| `visual`         | Generate a 2D knowledge graph visualization           |

---

## 5) AI Agent Integration (MCP)

Saurix is optimized for agentic workflows. The server exposes eight tools:

| Tool               | Arguments                                | Returns                                       |
| ------------------ | ---------------------------------------- | --------------------------------------------- |
| `index_repo`       | `source`, `out`                          | What was indexed, and where the graph landed  |
| `stats`            | `graph`                                  | Symbol, edge, language, and coverage totals   |
| `find_symbol`      | `graph`, `query`, `limit`                | Symbols whose name or id matches              |
| `callers`          | `graph`, `symbol`, `limit`               | `CALLS` edges pointing at the symbol          |
| `callees`          | `graph`, `symbol`, `limit`               | `CALLS` edges the symbol reaches              |
| `path_between`     | `graph`, `source`, `target`, `max_depth` | The shortest directed walk between two        |
| `impact_of_symbol` | `graph`, `symbol`, `depth`, `limit`      | The reverse neighbourhood of a change         |
| `related_files`    | `graph`, `file`, `depth`, `limit`        | Neighbour files of one file path              |

They help agents answer three kinds of question:

1. **Context Discovery**: `find_symbol` and `related_files`.
2. **Behavioral Mapping**: `callers`, `callees`, and `path_between`.
3. **Risk Assessment**: `impact_of_symbol`.

Every tool answers with the same envelope: `ok`, then either `data` or an
`error` of `code` and `message` (never both), then `meta` with the
`duration_ms` the call took. Tools that answer with rows add a `count` of them.
A failure is timed like a success, so the shape does not change with the outcome.

Reading a graph, or looking something up in it, fails the same way whichever
tool was asked:

| Code               | Meaning                                                        |
| ------------------ | -------------------------------------------------------------- |
| `GRAPH_NOT_FOUND`  | No graph at the path given, and none at the default path either |
| `INVALID_GRAPH`    | The file is not valid JSON, or not a Saurix graph              |
| `GRAPH_UNREADABLE` | The path exists but could not be read                          |
| `SYMBOL_NOT_FOUND` | The graph holds no symbol with the name or id given            |
| `FILE_NOT_FOUND`   | The graph holds no symbol belonging to the file path given     |
| `INVALID_SOURCE`   | `index_repo` was pointed at neither a path nor a GitHub URL     |

Two more sets of codes come from the tool's own work rather than its arguments:
`index_repo` reports `SOURCE_NOT_FOUND`, `PERMISSION_DENIED`, or `INDEX_FAILED`,
and a query that fails underneath a tool it had already accepted reports
`STATS_FAILED`, `FIND_FAILED`, `CALLERS_FAILED`, `CALLEES_FAILED`,
`PATH_FAILED`, `IMPACT_FAILED`, or `RELATED_FAILED`.

A search that matches nothing is not one of these: `find_symbol` returns an
empty list, and so does a `path_between` whose two ends the graph holds but
does not connect. A tool asked about a *specific* symbol is stricter, and
reports `SYMBOL_NOT_FOUND` rather than guessing which one was meant — pass an id
from `find_symbol` if a name is not enough.

Configure your agent with the `saurix-mcp` entry point. Once configured, the AI client (e.g., Claude Desktop) will automatically manage the server lifecycle—starting it in the background when needed and stopping it when the app closes. No manual terminal execution is required.

---

## 6) Development

### Running Tests

```bash
uv run pytest
```

### Regenerating the Documentation

The tool-call demo ([demo-mcp.md](demo-mcp.md)) and the agent walkthrough
([docs/agent-lifecycle.md](docs/agent-lifecycle.md)) are generated from a real
run of the MCP server against this repository, so every identifier in them is
one a reader can copy. Refresh them after touching the code or the tool surface:

```bash
uv run scripts/generate_mcp_demo.py
```

`--check` reports drift without writing. `tests/test_docs.py` re-runs the
generator on every test run and fails when the committed documents no longer
match the current code, or when any document names a module or file path that
no longer exists.

### Testing the MCP Server

You can test the MCP integration without a full IDE using the **MCP Inspector**:

1. **Install the Inspector**: `npm install -g @modelcontextprotocol/inspector`
2. **Run the Server**: `npx @modelcontextprotocol/inspector uv run saurix-mcp`
3. **Interact**: Open `http://localhost:5173`, click **Connect**, and use the **Call Tool** tab.

For step-by-step setup (Claude Desktop, Cursor, OpenCode), simply run `saurix init` in your project folder.

---

_Saurix is built for the era of autonomous coding._
