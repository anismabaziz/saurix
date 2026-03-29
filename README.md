# Code Atlas

Code Atlas turns a repo into a **knowledge graph** so humans and AI agents can explore code structure fast.

Instead of reading files one-by-one, you can ask:

- where a symbol is defined
- who calls it
- how two symbols are connected
- what may break if a symbol changes

---

## 1) One-minute mental model

```mermaid
flowchart LR
    A[Repo Path or GitHub URL] --> B[Scan Files]
    B --> C[Parse + Resolve Symbols]
    C --> D[Build Graph Nodes + Edges]
    D --> E[Query / Export / Visualize]
```

Think of it as:

- **Scanner** finds code files.
- **Extractors** read syntax and relationships.
- **Graph Store** saves structure.
- **Query Engine** answers navigation/debug questions.

---

## 2) How to run

Install dependencies first:

```bash
uv sync
```

Start the interactive CLI:

```bash
code-atlas
```

or:

```bash
uv run python main.py
```

Default graph file is:

`tmp/code-atlas.graph.json`

---

## 3) Typical workflow

```mermaid
sequenceDiagram
    participant U as You
    participant CLI as Code Atlas CLI
    participant IDX as Indexer
    participant G as Graph Store
    participant V as Browser Visual

    U->>CLI: index https://github.com/owner/repo
    CLI->>IDX: scan + parse + resolve
    IDX->>G: write tmp/code-atlas.graph.json
    U->>CLI: find auth
    CLI->>G: query nodes
    U->>CLI: callers python://pkg.auth:login
    CLI->>G: query edges
    U->>CLI: visual login
    CLI->>V: open interactive HTML subgraph
```

---

## 4) Commands (inside interactive shell)

```text
help
index <repo-or-github-url> [--out PATH]
load [PATH]
stats
find <name> [--limit N]
callers <symbol> [--limit N]
related <file> [--depth N] [--limit N]
path <from> <to> [--max-depth N]
impact <symbol> [--depth N] [--limit N]
export graphml [--out PATH]
export neo4j [--out DIR]
visual <symbol> [--depth N] [--limit N] [--out PATH]
raw on|off
where
clear
exit
```

### Stats quality reporting

`stats` now includes quality and coverage signals:

- confidence distribution (count + %) for edges: `high`, `medium`, `low`
- extraction coverage per language:
  - files seen
  - files indexed
  - coverage percentage
  - parser mode (`ast`, `tree-sitter`, `regex-fallback`, `stub`)

```mermaid
flowchart LR
    A[Extracted Edges] --> B[Confidence Buckets]
    B --> C[high/medium/low %]
    D[Scanned Files by Language] --> E[Indexed Files by Language]
    E --> F[Coverage % + Parser Mode]
    C --> G[stats panel]
    F --> G
```

---

## 5) What is a symbol?

A symbol is any named code entity represented in the graph.

```mermaid
flowchart TD
    A[module] --> B[class]
    A --> C[function]
    B --> D[method]
    C --> E[call target symbol]
```

Examples:

- `python://code_atlas.query` (module)
- `python://code_atlas.query:find_symbol` (function)
- `python://pkg.mod:Class.method` (method)

Tip: use `find <text>` first to discover valid symbol IDs.

---

## 6) Architecture (simple)

```mermaid
flowchart LR
    A[CLI Shell\ncode_atlas/cli/app.py] --> B[Repo Source\nrepo_source.py]
    B --> C[Scanner\nscanner.py]
    C --> D[Indexer\nindexer.py]
    D --> E1[Python Extractor\nextractors/python_extractor.py]
    D --> E2[TypeScript Extractor\nextractors/typescript_extractor.py]
    D --> E3[Go Extractor\nextractors/go_extractor.py]
    D --> E4[Stub Extractor\nextractors/stub_extractor.py]
    E1 --> F[Resolver\nimports/self/local symbols]
    E2 --> G[TS Nodes + Edges]
    E3 --> H2[Go Nodes + Edges]
    E4 --> G2[File Nodes]
    F --> H[Graph Store\ngraph.py + models.py]
    G --> H
    H2 --> H
    G2 --> H
    H --> I[Query Engine\nquery.py]
    H --> J[Exporters\nexporters.py]
    I --> K[find/callers/path/impact]
    J --> L[JSON/GraphML/Neo4j/HTML]
```

---

## 7) Parser flow (Python today)

```mermaid
flowchart TD
    A[Read .py file] --> B[ast.parse]
    B --> C[Collect imports + defs]
    C --> D[Walk classes/functions]
    D --> E[Extract calls + inheritance]
    E --> F[Resolve names best-effort]
    F --> G[Emit nodes + edges]
```

Edges currently include:

- `CONTAINS`
- `IMPORTS`
- `CALLS`
- `INHERITS`

Resolution is best-effort (Python is dynamic), so edges carry confidence.

---

## 8) Path + blast radius

```mermaid
flowchart LR
    A[path from A to B] --> B[Shortest directed traversal]
    C[impact X] --> D[Reverse traversal from X]
    B --> E[Debug dependency chains]
    D --> F[Estimate change risk]
```

- `path` helps explain how two symbols connect.
- `impact` shows likely upstream breakage surface.

---

## 9) Visualization + exports

```mermaid
flowchart LR
    A[Graph Store] --> B[visual <symbol>]
    A --> C[export graphml]
    A --> D[export neo4j]
    B --> E[Interactive HTML in browser]
    C --> F[Gephi / graph tools]
    D --> G[Neo4j import]
```

Default artifact locations (under git-ignored `tmp/`):

- `tmp/code-atlas.graph.json`
- `tmp/graph-view.html`
- `tmp/code-atlas.graphml`
- `tmp/neo4j/nodes.csv`
- `tmp/neo4j/edges.csv`

---

## 10) Example session

```text
index .
stats
find find_symbol
callers python://code_atlas.query:find_symbol
path python://code_atlas.cli:_cmd_interactive python://code_atlas.query:find_symbol
impact python://code_atlas.query:find_symbol --depth 3
visual find_symbol
export graphml --out tmp/repo.graphml
export neo4j --out tmp/neo4j
```

---

## 11) Current limitations

- Deep semantic extraction is strongest for Python right now.
- TypeScript and Go use Tree-sitter parsing when available, with regex fallback when parser dependencies are missing.
- Other languages currently use a fallback file-level extractor.
- Dynamic runtime behavior cannot be perfectly resolved statically.

---

## 12) Roadmap

```mermaid
flowchart LR
    A[Tree-sitter expansion\nJS/Java + richer TS/Go] --> B[Better symbol resolution]
    B --> C[Incremental indexing cache]
    C --> D[More query intelligence]
```
