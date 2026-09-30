# Why Saurix

## The problem I picked

Agents dropped into a checkout they have never seen do the slow thing first. They read files until the shape of the code appears, and fifty files to answer one question about a call chain is normal. Most of those tokens buy nothing. The bottleneck for an agent in an unfamiliar repo is not writing code. It is working out where it is.

I wanted that to be a lookup instead of a read.

## The approach

Static and local. One Extractor per language parses files with tree-sitter, Indexing merges the results into a Graph of Symbols and Edges, and Queries read that graph back: find the definition, list the callers, walk the path, measure the Impact. The MCP server is the same idea at the delivery end. Instead of pasting a codebase into a context window, the agent asks for the subgraph it needs.

I shipped an LLM `ask` command early on, three providers sitting behind a keychain, and dropped it again ten days later. What survived the removal was the idea underneath it. Send the subgraph, not the source. That is the shape of the MCP tool surface today, with no model in the loop at all.

## What surprised me

The surprises were all about measurement.

For six months my benchmarks measured two things, indexing speed and how many edges came out. Neither one asked whether the edges were real. I had a number I was proud of, and it did not mean what I thought it meant.

Then I traced `pallets/click` running its own test suite and compared the calls that actually happened against the edges I had inferred. 7.35%. I expected a static call graph to be mediocre against a real suite. I did not expect one confirmed call in thirteen.

The figure mattered less than the shape of the miss. 1884 of the 2333 unconfirmed calls are the same case: the pipeline saw the call and could not name what it pointed at. A method reached through an instance attribute, a helper handed over as a parameter, a call through `super()`. That is a limit of static inference rather than a defect in the parser, and no amount of work on tree-sitter grammars was ever going to move it. Knowing that in the first week would have saved me a lot of guessing.

A hand-labeled sample of ordinary module code came out at 98.21%, and I kept the two figures apart on purpose. They are different populations measured by different means, and averaging them would describe neither. The high figure says the pipeline reads plain code well. The low one says the calls a test suite makes are mostly the ones no static reader can resolve.

The last surprise was the incremental cache. I built it in March because indexing a large repo was slow. In the September simplification I deleted it as complexity that was not paying for itself. Twenty-seven days later I rebuilt the same file with the same helper names, because the complexity had been load-bearing the entire time. I should have left it alone.

## What I would do differently

Measure correctness before speed. The accuracy work should have come first, because it would have changed what I spent the six months optimizing.

The report is a published snapshot and not a CI gate. Tracing a foreign repository means installing its dependencies and pinning it to one commit, which is slow and breaks for reasons that have nothing to do with this repo. Turning it into a scheduled check needs three things I do not have: a container image so the run does not depend on the machine, a recorded floor for the figure so a regression fails instead of surprising me, and a maintained list of targets instead of the single one measured here. Until those exist the number stays published, pinned to its commit, and reproducible with one command, `uv run scripts/accuracy.py`. The method and every miss behind it are in [accuracy.md](accuracy.md).

Two limits belong next to the figure rather than in a footnote. Only Python is traced, so nothing in the report says how well the Go, Java, and TypeScript edges are inferred. And recall is not measured and not claimed, because an edge on a path the suite never executed is not a false negative.

The last thing is the one I keep coming back to. Most of the deletions in this history left no reason behind. The AI command went into a one-line commit with no rationale, five months before the simplification pass that removed half the codebase. The two decisions I did write down, the `Node` to `Symbol` rename and the choice to judge accuracy against a trace rather than against another static analyzer, are the only two I can still defend cleanly. The reason is worth ten seconds to type at the moment you delete something. Otherwise it dies with the context, and six months later you are looking at a commit that tells you what disappeared but not why.

Start with [agent-lifecycle.md](agent-lifecycle.md) to watch an agent use the graph end to end, or [architecture.md](architecture.md) for how the pieces fit.
