# ADR 0002: Judge accuracy against a runtime trace, publish the report as a snapshot

Status: accepted (shipped in 0.3.0)

## Context

The benchmarks said how fast indexing was and how many edges it found, but nothing said how many of those edges were real. I needed a ground truth to check CALLS edges against.

## Decision

Trace the target repo's own test suite at runtime and diff the calls that really happened against the edges indexing inferred. The report states precision on observed calls and claims no recall, because a path the suite never runs is not a miss. A hand-labeled sample covers code the trace cannot reach and stays a second, separate figure.

Comparing against another static analyzer was the alternative and I rejected it. That only measures where two guesses agree. A trace records what the code actually did, which is the only ground truth worth the name.

The report is a published snapshot, not a CI gate. It needs a foreign checkout, its dependencies, and its suite, which is slow and breaks for reasons that have nothing to do with this repo. Regenerating it is one command. Promoting it to a scheduled check would need a container image, a recorded floor for the figure, and more than one target.
