# ADR 0001: Rename Node to Symbol with no alias

Status: accepted (shipped in 0.3.0)

## Context

The code called the graph node type Node while the terms the project documents, and all the docs written from them, called it Symbol. Every new reader had to learn two words for one thing.

## Decision

Rename Node to Symbol in 0.3.0 and ship no deprecation alias. The old import fails loudly, the changelog names the old name, the new name, and the edit to make, and graph JSON from earlier versions is refused with a re-index message instead of being read silently.

An alias was the alternative and I rejected it. It would have kept both vocabularies alive in imports, error messages, and serialized graphs, which is exactly the mismatch the rename was meant to kill. Pre-1.0 is the cheap place to break a public name, and the project tells users so up front in the changelog.

## Consequences

Users rename the import and re-index old graphs. Nothing else changes. Fields, ids, and edge types are identical.
