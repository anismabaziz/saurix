# Why Saurix

Agents dropped into a repo they have never seen do the slow thing first: read files until the shape appears. Fifty files to answer one question about a call chain is normal, and most of those tokens buy nothing. Saurix exists to skip that part. It indexes the checkout once, into a graph of Symbols and Edges, and then every structural question is a lookup.

The approach is static and local. One Extractor per language parses files with tree-sitter, Indexing merges the results into a Graph, and Queries read it back: find the definition, list the callers, walk the path, measure the Impact. The MCP server is the delivery end of the same idea. Instead of pasting a codebase into a context window, the agent asks for the subgraph it needs.

The honest part is the accuracy report. On `pallets/click`, 7.35% of the calls the test suite actually made were edges the pipeline had inferred. Calls through parameters, instance attributes, and decorators are the bulk of the misses, and [docs/accuracy.md](accuracy.md) lists them instead of averaging them away. A hand-labeled sample of ordinary module code scores far higher, which says the pipeline reads plain code well and struggles where any static reader would.

What I would do differently is also written down. The report is a snapshot, not a CI gate, because tracing a foreign repo on every push would be slow and fragile. Promoting it to a scheduled check needs a container image, a recorded floor for the figure, and more than one target. Until then the number stays published, pinned to its commit, and reproducible with one command: `uv run scripts/accuracy.py`.

Start with [agent-lifecycle.md](agent-lifecycle.md) to see an agent use the graph end to end, or [architecture.md](architecture.md) for how the pieces fit.
