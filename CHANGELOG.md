# Changelog

All notable changes to Saurix are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[semantic versioning](https://semver.org/spec/v2.0.0.html). Saurix is pre-1.0, so a
minor bump may still break an API.

## [0.3.0]

The release where the code stopped calling its own model something the project never
did in its glossary.

### Changed

- **`Node` is now `Symbol`.** The graph model is named after the terms the project
  documents. `Edge` was already right and kept its name.
- **The store speaks the same vocabulary.** `GraphStore.nodes` is `GraphStore.symbols`,
  `add_node` is `add_symbol`, and `get_nodes_by_name` is `get_symbols_by_name`. The
  serialized graph writes `symbols` instead of `nodes`, and the `stats` tool reports
  `symbols` and `symbol_types` instead of `nodes` and `node_types`.
- **Graph files carry a new schema version.** The graph schema is now `2.0.0`. A graph
  written by 0.2.0 or earlier is refused with a message telling you to re-index,
  rather than being read as an empty graph. The interactive shell reports the refusal
  and starts with no graph loaded, so you can re-index in the same session.
- **The parser dependency is no longer archived.** `tree-sitter-languages` is gone in
  favour of `tree-sitter-language-pack`, and the regex fallback that existed to survive
  its absence is deleted. Every language now goes through tree-sitter.
- **The version is read from one place.** `saurix.__version__` comes from the installed
  package metadata. It used to be written out twice, and the two copies disagreed:
  `saurix.__version__` said `0.1.0` while PyPI had `0.2.0`.

### Removed

- **No deprecation alias for `Node`.** Breaking a public name in a pre-1.0 release is
  cheaper now than carrying two vocabularies forever. `from saurix.core import Node`
  raises `ImportError`.

### Migrating from 0.2.0

Rename the import and the call sites. Nothing else changes: the fields, the ids, and
the edges are identical.

```python
# before
from saurix.core import Edge, Node

graph.add_node(Node(id="python://app:handler", type="function", ...))
count = graph.stats()["nodes"]

# after
from saurix.core import Edge, Symbol

graph.add_symbol(Symbol(id="python://app:handler", type="function", ...))
count = graph.stats()["symbols"]
```

If you read `graph.nodes` or call `add_node`, the same rename applies. Graph JSON
written by 0.2.0 has to be regenerated:

```bash
saurix index . --out saurix.graph.json
```

The dashboard still receives a `nodes` key, because that is what the force-graph
library it renders with expects. Nothing in Saurix calls them that any more.

[0.3.0]: https://github.com/anismabaziz/saurix/compare/v0.2.0...v0.3.0
