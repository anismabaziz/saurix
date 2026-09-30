# Contributing

Thanks for picking up Saurix. This is a small codebase and I try to keep it that way, so most contributions are fixes to the extractors, the query layer, or the docs that describe them.

## Setup

You need Python 3.12 and uv. Anything else gets installed from the lockfile.

```bash
uv sync
```

That gives you the CLI (`saurix`), the MCP server (`saurix-mcp`), and the dev tools (pytest, ruff, mypy). I work from a source checkout with `uv run` in front of everything:

```bash
uv run saurix index . --out /tmp/saurix.graph.json
uv run saurix-mcp
```

If you use pip instead, `pip install -e ".[dev]"` works, but CI runs everything through uv, so that is what I test against.

## Before you open a pull request

Run the full check locally. It is the same four commands CI runs:

```bash
uv run ruff check .
uv run ruff format . --check
uv run mypy saurix
uv run pytest --cov=saurix --cov-report=term-missing -q
```

A few notes on what those enforce:

- Ruff handles lint and formatting. No separate formatter config to argue about.
- Mypy runs over the `saurix` package. If you add a new module, keep it typed. Asserts after graph guards are fine, the codebase already uses them where the type checker cannot see through a boolean helper.
- Tests live in `tests/`. If you change extractor output or tool responses, add or update a test next to the change rather than in a separate PR.
- Two generated docs have to stay in sync with the code. `tests/test_docs.py` fails when they drift, so after touching the tool surface or the CLI run:

```bash
uv run scripts/generate_mcp_demo.py
```

That refreshes `demo-mcp.md` and `docs/agent-lifecycle.md`. Commit the result with your change.

The accuracy report (`docs/accuracy.md`) is different. It clones a foreign repo and traces its test suite, which is too slow for a pre-push check. Do not regenerate it unless you changed call edge inference. If you did, run `uv run scripts/accuracy.py` and mention the before and after numbers in the PR.

## What review looks like

I review every PR myself. Here is what I actually check:

- Small scope. One behavior change per PR. If you found two problems, open two PRs.
- Tests that fail without the fix. I will ask for them if they are missing.
- No drive-by refactors. Renames and file moves go in their own commit so the behavior change stays readable.
- Docs match the code. If the README or `docs/architecture.md` describes what you changed, update it in the same PR.
- Commit messages use the conventional shape (`feat:`, `fix:`, `docs:`, and so on) with a short imperative subject. One clean commit per PR unless there is a reason to split.

I aim to reply within a few days. If CI is green and the change is small, that is usually one round. Larger changes to indexing or the graph schema get more questions, mostly about backward compatibility and what happens to graphs written by older versions.
