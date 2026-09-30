# Demo assets

Four files, all captured from real runs of the tool. Nothing here is mocked up,
and nothing here is drawn by hand.

| File                  | What it shows                                                               |
| --------------------- | --------------------------------------------------------------------------- |
| `saurix-demo.gif`     | A terminal session: `init`, `stats`, `find`, `impact` against a checkout    |
| `cli-workflow.png`    | The last screen of that same session, with the `find` and `impact` results  |
| `visual-workflow.png` | The dashboard `init` generated, in a headless browser                        |
| `mcp-workflow.png`    | Three MCP tool calls, and the payloads they returned                        |

`visual-workflow.png` is also the image the portfolio site uses for the Saurix
card. It is captured once and referenced from both places, so the card and this
file cannot drift apart.

## Regenerating them

```bash
uv run scripts/capture_demo.py
```

The script copies the checkout it is given (this one by default) into
`/tmp/saurix-demo`, runs the CLI there through a pseudo-terminal, and writes the
four files above. The copy exists so the paths the CLI prints stay short: the
tables it draws would wrap otherwise, and the whole session is on screen.

What it does with the run:

- The session is recorded at the speed it happened, then rescaled onto about 21
  seconds. Indexing takes as long as it takes, and nobody watches that at real
  speed. No frame is shortened below 80 ms, so nothing flashes past either.
- The dashboard is photographed by Chromium at 1280x800 once the force layout
  has settled, then written as a 128-colour PNG, which on a dark background is
  indistinguishable from the original and a third of the bytes.
- The MCP calls come from `scripts/generate_mcp_demo.py`, the generator that
  writes `demo-mcp.md`, so every identifier in the screenshot is one a reader can
  copy out of the documentation and run. The responses are shown as the tool
  sent them, cut where a picture has to cut them, with a line saying how many
  lines went missing.

## What it needs

- Pillow, for painting the frames. It is in the dev group.
- Playwright with a Chromium build: `uv run playwright install chromium`.
- A monospaced font that can draw box-drawing characters. Menlo, SF Mono, DejaVu
  Sans Mono, and Consolas are looked for in that order. Set
  `SAURIX_CAPTURE_FONT` to a font file to override.
- Network, once. The dashboard loads force-graph from unpkg, and the capture
  fetches the pinned bundle (currently 1.52.0) into `tmp/capture/` before
  inlining it into a copy of the page. Reruns read the cache.

## What keeps them honest

`tests/test_capture.py` holds five things: every image the README shows exists
at the path it names, the README still shows the recording and the three
screenshots, the script names no asset it does not publish, no capture is bigger
than its own budget, and the four together fit a budget of their own.

The budgets are the reason the recording is a GIF and not a video. At 190
frames, 128 colours and a shared palette it lands around 190 KB; the dashboard
shot is 148 KB after quantisation; the whole set is about 520 KB, which is
roughly what this repository weighed before it carried the assets.

`uv run scripts/capture_demo.py --check` runs the existence and size half of
that on demand.

## When the numbers in them go stale

The recording and the dashboard are a snapshot, not a live view. Symbol counts
move as the code does. Nothing in CI compares them, because there is no honest
way to: the font, the browser build, and the force layout all differ between
machines, so a byte comparison would fail on a working tree that is fine.
Rerunning the script is the whole fix, and it takes about forty seconds.
