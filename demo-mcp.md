# MCP Demo (Code Atlas)

This demo shows a simple MCP workflow with 5 tool calls and expected response shapes.

## Prerequisites

- Run `uv sync`
- Start MCP server: `code-atlas-mcp`

## 1) Index a repo

Tool call:

```json
{
  "tool": "index_repo",
  "arguments": {
    "source": "https://github.com/anismabaziz/code-atlas"
  }
}
```

Expected response shape:

```json
{
  "ok": true,
  "data": {
    "graph_path": ".../tmp/code-atlas.graph.json",
    "source_kind": "github:anismabaziz/code-atlas",
    "scanned_files": 30,
    "indexed_files": 30,
    "stats": { "nodes": 0, "edges": 0 }
  },
  "meta": { "duration_ms": 0 }
}
```

## 2) Read graph stats

Tool call:

```json
{
  "tool": "stats",
  "arguments": {
    "graph": "tmp/code-atlas.graph.json"
  }
}
```

Expected response includes:

- `confidence_counts`
- `confidence_percentages`
- `extraction_coverage`

## 3) Find a symbol

Tool call:

```json
{
  "tool": "find_symbol",
  "arguments": {
    "graph": "tmp/code-atlas.graph.json",
    "query": "find_symbol",
    "limit": 10
  }
}
```

Expected response:

```json
{
  "ok": true,
  "data": [
    {
      "id": "python://code_atlas.query.basic:find_symbol",
      "type": "function",
      "name": "find_symbol",
      "file": "code_atlas/query/basic.py"
    }
  ],
  "meta": { "count": 1, "duration_ms": 0 }
}
```

## 4) Find path between symbols

Tool call:

```json
{
  "tool": "path_between",
  "arguments": {
    "graph": "tmp/code-atlas.graph.json",
    "source": "python://code_atlas.cli.commands:cmd_find",
    "target": "python://code_atlas.query.basic:find_symbol",
    "max_depth": 12
  }
}
```

Expected response:

- `ok: true`
- `data`: list of path steps (`step`, `edge`, `id`, `type`, `name`)

## 5) Impact analysis

Tool call:

```json
{
  "tool": "impact_of_symbol",
  "arguments": {
    "graph": "tmp/code-atlas.graph.json",
    "symbol": "python://code_atlas.query.basic:find_symbol",
    "depth": 3,
    "limit": 50
  }
}
```

Expected response:

- `ok: true`
- `data`: reverse-neighborhood rows (`distance`, `via`, `id`, `type`, `name`, `file`)
