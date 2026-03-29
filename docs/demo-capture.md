# Demo Capture Guide

Run this once to generate deterministic demo artifacts:

```bash
uv run python scripts/demo_runs.py
```

This creates:

- `docs/assets/demo-run/cli-stats.json`
- `docs/assets/demo-run/cli-find.json`
- `docs/assets/demo-run/cli-path.json`
- `docs/assets/demo-run/cli-impact.json`
- `docs/assets/demo-run/mcp-find-symbol.json`
- `docs/assets/demo-run/mcp-impact-symbol.json`
- `docs/assets/demo-run/visual-workflow.html`
- `docs/assets/demo-run/transcript.txt`

Then capture and save your portfolio files:

- `docs/assets/cli-workflow.png`
- `docs/assets/visual-workflow.png`
- `docs/assets/mcp-workflow.png`
- `docs/assets/code-atlas-demo.gif`

Suggested recording flow for the GIF:

1. Start CLI and run `index .`, `stats`, `find find_symbol`, `path ...`, `impact ...`
2. Open `docs/assets/demo-run/visual-workflow.html` and show filters/path highlight
3. Show MCP JSON outputs in `docs/assets/demo-run/mcp-find-symbol.json` and `docs/assets/demo-run/mcp-impact-symbol.json`
