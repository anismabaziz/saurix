# MCP Demo (Saurix)

This demo shows a simple MCP workflow with 5 tool calls and expected response shapes.

## Prerequisites

- Run `uv sync`
- Start MCP server: `saurix-mcp`

## 1) Index a repo

Tool call:

```json
{
  "tool": "index_repo",
  "arguments": {
    "source": "https://github.com/anismabaziz/saurix"
  }
}
```

Expected response shape:

```json
{
  "ok": true,
  "data": {
    "graph_path": ".../tmp/saurix.graph.json",
    "source_kind": "github:anismabaziz/saurix",
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
    "graph": "tmp/saurix.graph.json"
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
    "graph": "tmp/saurix.graph.json",
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
      "id": "python://saurix.query.basic:find_symbol",
      "type": "function",
      "name": "find_symbol",
      "file": "saurix/query/basic.py"
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
    "graph": "tmp/saurix.graph.json",
    "source": "python://saurix.cli.commands:cmd_find",
    "target": "python://saurix.query.basic:find_symbol",
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
    "graph": "tmp/saurix.graph.json",
    "symbol": "python://saurix.query.basic:find_symbol",
    "depth": 3,
    "limit": 50
  }
}
```

Expected response:

- `ok: true`
- `data`: reverse-neighborhood rows (`distance`, `via`, `id`, `type`, `name`, `file`)
