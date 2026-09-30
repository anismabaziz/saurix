"""
Demo Capture

Regenerates what the README leads with: a short terminal recording of a real
Saurix session, and screenshots of that session, the generated dashboard, and an
agent's tool calls. Nothing here is drawn by hand. The session is driven through
a pseudo-terminal against a real checkout, the dashboard is photographed by a
headless browser, and the tool calls come out of the live MCP server, so a
reader who follows the README sees exactly what the recording shows.

The dashboard capture doubles as the portfolio card image, which is why it is
written once and referenced from both places.

Usage:
    uv run scripts/capture_demo.py
    uv run scripts/capture_demo.py --source ../some/other/checkout
    uv run scripts/capture_demo.py --check
"""

from __future__ import annotations

import argparse
import codecs
import fcntl
import importlib.util
import io
import json
import os
import pty
import re
import select
import shutil
import signal
import struct
import subprocess
import sys
import termios
import time
import urllib.request
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass, replace
from pathlib import Path
from types import ModuleType
from typing import Any

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = REPO_ROOT / "docs" / "assets"

# What the README shows on its first screen. The dashboard is the portfolio
# card image as well, so it is listed once.
ASSETS = (
    "docs/assets/saurix-demo.gif",
    "docs/assets/cli-workflow.png",
    "docs/assets/visual-workflow.png",
    "docs/assets/mcp-workflow.png",
)

# A capture that grows without limit turns a half-megabyte repository into a
# slow clone, so the assets are held to a budget each and to one between them.
# The set is meant to cost roughly what the repository cost before it.
ASSET_BUDGET_BYTES = 300_000
ASSET_TOTAL_BUDGET_BYTES = 700_000

# The dashboard loads force-graph from a CDN. The capture pins the version so a
# regeneration paints the same graph rather than whatever the CDN serves that
# day; the version is recorded in docs/assets/README.md.
FORCE_GRAPH_VERSION = "1.52.0"
FORCE_GRAPH_URL = (
    f"https://unpkg.com/force-graph@{FORCE_GRAPH_VERSION}/dist/force-graph.min.js"
)

# Rows of the MCP transcript, which is a laid-out page of calls rather than a
# scrolled session and so is allowed to be taller than the terminal.
MCP_ROWS = 40

# Terminal geometry of the recording. Wide enough for the widest table the CLI
# draws, short enough to read at README width.
COLS = 96
ROWS = 26

# Recording cadence. Frames are sampled while the run happens, then paced to a
# length a stranger will sit through.
SAMPLE_SECONDS = 0.035
TYPE_SECONDS = 0.085
MIN_FRAME_MS = 80
TARGET_MS = 21_000
MAX_FRAMES = 190
GIF_COLORS = 128

FONT_SIZE = 13
PADDING = 14

# Colours lifted from the dashboard's own stylesheet, so the recording and the
# screenshot of the dashboard look like the same product.
BACKGROUND = (13, 17, 23)
CHROME = (22, 27, 34)
FOREGROUND = (201, 209, 217)
BORDER = (48, 54, 61)
MUTED = (110, 118, 129)
ACCENT = (88, 166, 255)
POSITIVE = (63, 185, 80)

FONT_CANDIDATES = (
    "/System/Library/Fonts/Menlo.ttc",
    "/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/SFNSMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    "C:/Windows/Fonts/consola.ttf",
)

# Copied to a scratch directory so the recorded paths are short enough to fit
# the tables the CLI draws, and so the capture never depends on a stale graph
# sitting in the source checkout.
COPY_IGNORES = (
    ".git",
    ".venv",
    ".coverage",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
    "saurix.graph.json",
    "saurix.html",
    "tmp",
)

MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\(\s*([^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")


class CaptureError(RuntimeError):
    """
    Raised when a capture cannot be taken, with a message worth acting on.
    """


def _load(name: str, path: Path) -> ModuleType:
    """
    Import a script from the scripts directory, which is not a package.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise CaptureError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# The documentation generator, which is also what the MCP transcript replays. The
# symbol the demo is about is read out of it rather than copied, so a refactor
# that moves `build_graph` moves the recording with it or fails the run.
DEMO = _load("generate_mcp_demo", REPO_ROOT / "scripts" / "generate_mcp_demo.py")
DEMO_QUERY = DEMO.DEMO_QUERY
DEMO_SYMBOL = DEMO.CALL_TARGET

# --------------------------------------------------------------------------- #
# Terminal emulation
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Style:
    """
    The attributes of a run of characters that a recording has to show.

    Backgrounds are deliberately absent: nothing in the captured output uses
    them, and a flat background keeps the GIF small.
    """

    foreground: tuple[int, int, int] | None = None
    bold: bool = False
    dim: bool = False


@dataclass(frozen=True)
class Span:
    """
    A run of characters sharing one style, which is what the renderer draws.
    """

    text: str
    style: Style


Cell = tuple[str, Style]
Row = tuple[Cell, ...]

# Rich's console markup, which the CLI prints with and the MCP transcript is
# laid out in. A leading slash closes the tag; an empty name closes the lot.
MARKUP = re.compile(r"\[/?([a-z ]*)\]")
MARKUP_STYLES = {
    "bold": Style(bold=True),
    "dim": Style(dim=True),
    "cyan": Style(foreground=ACCENT),
    "bold cyan": Style(foreground=ACCENT, bold=True),
    "green": Style(foreground=POSITIVE),
    "bold green": Style(foreground=POSITIVE, bold=True),
}


def xterm256(index: int) -> tuple[int, int, int]:
    """
    Return the RGB value of one of the 256 terminal colours.

    The table is computed rather than transcribed, so the cube and the ramp
    cannot drift from the definition they come from.
    """
    if not 0 <= index <= 255:
        raise ValueError(f"not a terminal colour: {index}")
    if index < 16:
        base = (
            (0, 0, 0),
            (128, 0, 0),
            (0, 128, 0),
            (128, 128, 0),
            (0, 0, 128),
            (128, 0, 128),
            (0, 128, 128),
            (192, 192, 192),
        )
        return base[index] if index < 8 else _lighten(base[index - 8])
    if index < 232:
        offset = index - 16
        levels = (0, 95, 135, 175, 215, 255)
        return (levels[offset // 36], levels[(offset // 6) % 6], levels[offset % 6])
    grey = 8 + (index - 232) * 10
    return (grey, grey, grey)


def _lighten(colour: tuple[int, int, int]) -> tuple[int, int, int]:
    """
    Brighten one of the eight base colours the way terminals do.
    """
    red, green, blue = colour
    return (min(255, red * 3 // 2), min(255, green * 3 // 2), min(255, blue * 3 // 2))


def _blank_row(cols: int) -> list[Cell]:
    """
    Return an empty row of the given width.
    """
    return [(" ", Style()) for _ in range(cols)]


class Screen:
    """
    A terminal, held in memory, fed whatever a child process wrote to it.

    Enough of the escape grammar is implemented for the output Rich produces
    under a pseudo-terminal: line feeds, carriage returns, and SGR colour. The
    sequences a recording never needs to show are consumed and dropped.
    """

    def __init__(self, cols: int = COLS) -> None:
        self.cols = cols
        self._rows: list[list[Cell]] = [_blank_row(cols)]
        self._row = 0
        self._col = 0
        self._style = Style()
        self._pending = ""
        # A terminal wraps on the character after the one that fills the last
        # column, not on the one that fills it. Rich relies on that: it redraws
        # a full-width progress line with a carriage return, and a terminal that
        # had already moved down would lose the row.
        self._wrap = False

    def feed(self, data: str) -> None:
        """
        Write decoded output to the screen.

        A read from the child can end in the middle of an escape sequence, so a
        fragment is held back until the rest of it arrives. Printing the
        fragment instead would put `[2m` on the recording.
        """
        data = self._pending + data
        self._pending = ""
        index = 0
        while index < len(data):
            char = data[index]
            if char == "\x1b":
                end = self._escape(data, index)
                if end < 0:
                    self._pending = data[index:]
                    return
                index = end
                continue
            index += 1
            if char == "\n" or char == "\x0b" or char == "\x0c":
                self._move_to(self._row + 1, 0)
            elif char == "\r":
                self._col = 0
                self._wrap = False
            elif char == "\b":
                self._col = max(0, self._col - 1)
            elif char == "\t":
                self._col = min(self.cols - 1, (self._col // 8 + 1) * 8)
            elif char == "\x07":
                continue
            else:
                self._put(char)

    def write(self, text: str, style: Style) -> None:
        """
        Write text in one style, as a program building a screen would.

        The captures that are not a recorded session compose their own lines;
        this is how they put styled text on the screen.
        """
        previous = self._style
        self._style = style
        try:
            self.feed(text)
        finally:
            self._style = previous

    def rows(self) -> list[Row]:
        """
        Return the rows with content, without the empty ones trailing them.
        """
        trimmed = [self._trim(row) for row in self._rows]
        while trimmed and not any(trimmed[-1]):
            trimmed.pop()
        return [tuple(row) for row in trimmed]

    def text(self) -> str:
        """
        Return the visible text of every row with content, one row per line.
        """
        return "\n".join("".join(cell[0] for cell in row) for row in self.rows())

    def last_line(self) -> str:
        """
        Return the text of the row the cursor is on.
        """
        return "".join(cell[0] for cell in self._rows[self._row])

    def _trim(self, row: list[Cell]) -> list[Cell]:
        """
        Drop the trailing blank cells of a row, which carry no information.
        """
        end = len(row)
        while end and row[end - 1][0] == " " and row[end - 1][1] == Style():
            end -= 1
        return row[:end]

    def _current(self) -> list[Cell]:
        """
        Return the row the cursor is on, extending it when needed.
        """
        while len(self._rows) <= self._row:
            self._rows.append(_blank_row(self.cols))
        return self._rows[self._row]

    def _move_to(self, row: int, col: int) -> None:
        """
        Put the cursor somewhere, clamped to the terminal.
        """
        self._row = max(0, row)
        self._col = min(max(0, col), self.cols - 1)
        self._wrap = False
        self._current()

    def _put(self, char: str) -> None:
        """
        Write one character at the cursor, overwriting what was there, and wrap
        to the next row when the last column has been filled.
        """
        if self._wrap:
            self._move_to(self._row + 1, 0)
        row = self._current()
        row[self._col] = (char, self._style)
        self._col += 1
        if self._col >= self.cols:
            self._col = self.cols - 1
            self._wrap = True

    def _erase_line(self, mode: int) -> None:
        """
        Implement the three erase-in-line modes.
        """
        row = self._current()
        if mode == 0:
            del row[self._col :]
        elif mode == 1:
            for index in range(min(self._col + 1, len(row))):
                row[index] = (" ", Style())
        else:
            self._rows[self._row] = _blank_row(self.cols)

    def _escape(self, data: str, start: int) -> int:
        """
        Return the index just past one escape sequence, or -1 if it is cut off.

        Almost every sequence is two characters long, so anything else has to be
        looked for; a sequence whose end has not arrived yet is reported as
        incomplete rather than swallowed.
        """
        kind = data[start + 1 : start + 2]
        if kind == "[":
            return self._control(data, start)
        if kind in "P^_":  # Device control, privacy message, or a string command
            end = data.find("\x1b\\", start + 2)
            bell = data.find("\x07", start + 2)
            if end == -1 and bell == -1:
                return -1
            return (end + 2) if end != -1 and (bell == -1 or end < bell) else bell + 1
        if kind == "]":  # Operating system command, ended by a bell
            bell = data.find("\x07", start + 2)
            return -1 if bell == -1 else bell + 1
        if not kind:
            return -1
        return start + 2

    def _control(self, data: str, start: int) -> int:
        """
        Consume a control sequence and apply the part that is visible.
        """
        cursor = start + 2
        # Parameter and intermediate bytes run from space to `?`; the byte after
        # them is the final byte that says what the sequence does.
        while cursor < len(data) and " " <= data[cursor] <= "?":
            cursor += 1
        if cursor >= len(data):
            return -1
        final, arguments = data[cursor], data[start + 2 : cursor]
        private = arguments.startswith("?")
        numbers = [
            int(part) for part in arguments.lstrip("?").split(";") if part.isdigit()
        ]
        first = numbers[0] if numbers else 0

        if not private:
            if final == "m":
                self._sgr(numbers or [0])
            elif final == "K":
                self._erase_line(first)
            elif final == "J" and first in (2, 3):
                self._rows = [_blank_row(self.cols)]
                self._row = self._col = 0
            elif final == "A":
                self._move_to(self._row - max(1, first), self._col)
            elif final == "B":
                self._move_to(self._row + max(1, first), self._col)
            elif final == "C":
                self._move_to(self._row, self._col + max(1, first))
            elif final == "D":
                self._move_to(self._row, self._col - max(1, first))
            elif final in "Hf":
                row = (numbers[0] if numbers else 1) - 1
                col = (numbers[1] if len(numbers) > 1 else 1) - 1
                self._move_to(row, col)
            elif final == "G":
                self._move_to(self._row, first - 1)
        return cursor + 1

    def _sgr(self, numbers: list[int]) -> None:
        """
        Apply one SGR sequence to the current style.
        """
        index = 0
        while index < len(numbers):
            code = numbers[index]
            if code == 0:
                self._style = Style()
            elif code == 1:
                self._style = replace(self._style, bold=True)
            elif code == 2:
                self._style = replace(self._style, dim=True)
            elif code == 22:
                self._style = replace(self._style, bold=False, dim=False)
            elif code == 39:
                self._style = replace(self._style, foreground=None)
            elif 30 <= code <= 37:
                self._style = replace(self._style, foreground=xterm256(code - 30))
            elif 90 <= code <= 97:
                self._style = replace(self._style, foreground=xterm256(code - 90 + 8))
            elif code in (38, 48) and index + 1 < len(numbers):
                consumed, colour = _extended_colour(numbers, index)
                index += consumed
                if code == 38 and colour is not None:
                    self._style = replace(self._style, foreground=colour)
            index += 1


def _extended_colour(
    numbers: list[int], index: int
) -> tuple[int, tuple[int, int, int] | None]:
    """
    Read the arguments of a 256-colour or truecolour SGR code.

    Returns how many extra arguments were consumed and the colour they name, or
    `None` for a form this recording never sees.
    """
    mode = numbers[index + 1] if index + 1 < len(numbers) else 0
    if mode == 5 and index + 2 < len(numbers):
        return 2, xterm256(numbers[index + 2])
    if mode == 2 and index + 4 < len(numbers):
        red, green, blue = numbers[index + 2 : index + 5]
        return 4, (red, green, blue)
    return 1, None


def window(screen: Screen, height: int) -> list[str]:
    """
    Return the last `height` rows a reader would see, as plain text.
    """
    lines = ["".join(cell[0] for cell in row) for row in screen.rows()]
    return lines[-height:] if height > 0 else []


def window_rows(screen: Screen, height: int) -> list[Row]:
    """
    Return the styled rows of the recording window, padded to `height`.
    """
    rows = screen.rows()[-height:] if height > 0 else []
    padding = [(" ", Style())] * (height - len(rows))
    return list(rows) + [tuple(padding) for _ in range(len(padding))]


def spans(row: Row) -> list[Span]:
    """
    Split a row into the runs of same-styled cells the renderer draws.
    """
    runs: list[Span] = []
    for char, style in row:
        if runs and runs[-1].style == style:
            runs[-1] = Span(runs[-1].text + char, style)
        else:
            runs.append(Span(char, style))
    return [run for run in runs if run.text.strip() or run.style != Style()]


def style_of(screen: Screen, row: int, column: int) -> Style:
    """
    Return the style of one cell, for checking what the parser understood.
    """
    return screen.rows()[row][column][1]


# --------------------------------------------------------------------------- #
# Pacing
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Frame:
    """
    One screen as it was on show, and for how long.
    """

    rows: tuple[Row, ...]
    duration_ms: int


def dedupe(frames: Sequence[Frame]) -> list[Frame]:
    """
    Collapse consecutive frames that show the same screen.

    Sampling a real run produces a lot of them, and they are the dead time that
    makes a recording feel long. The time they took moves onto the frame that
    stayed, so nothing is cut from the playback.
    """
    kept: list[Frame] = []
    for frame in frames:
        if kept and kept[-1].rows == frame.rows:
            kept[-1] = replace(
                kept[-1], duration_ms=kept[-1].duration_ms + frame.duration_ms
            )
        else:
            kept.append(frame)
    return kept


def thin(frames: Sequence[Frame], limit: int) -> list[Frame]:
    """
    Sample a long capture down to `limit` frames, keeping its total length.

    Keeping the first and last frames matters: the first is what a reader sees
    when the page loads, and the last is what the still is taken from.
    """
    if len(frames) <= limit:
        return list(frames)
    if limit < 2:
        return [frames[-1]]
    kept: list[Frame] = []
    previous = 0
    elapsed = 0
    for position in range(limit):
        index = round(position * (len(frames) - 1) / (limit - 1))
        elapsed += sum(frame.duration_ms for frame in frames[previous : index + 1])
        kept.append(replace(frames[index], duration_ms=elapsed))
        previous = index + 1
    return kept


def pace(frames: Sequence[Frame], target_ms: int, min_ms: int) -> list[Frame]:
    """
    Rescale real frame timings onto a length a stranger will watch.

    Indexing a repository takes as long as it takes; nobody watches that at
    real speed. Durations are scaled by one factor, so the pauses stay in
    proportion, and no frame is shortened below the floor that keeps the
    animation alive.
    """
    if not frames:
        return []
    total = sum(frame.duration_ms for frame in frames)
    scale = target_ms / total if total else 0.0
    return [
        replace(frame, duration_ms=max(min_ms, round(frame.duration_ms * scale)))
        for frame in frames
    ]


# --------------------------------------------------------------------------- #
# Painting
# --------------------------------------------------------------------------- #


def find_font() -> Path:
    """
    Return a monospaced font that can draw box-drawing characters.
    """
    override = os.environ.get("SAURIX_CAPTURE_FONT")
    candidates = (override,) if override else FONT_CANDIDATES
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    raise CaptureError(
        "no monospaced font found for the capture; set SAURIX_CAPTURE_FONT to a "
        f"font file. Tried: {', '.join(c for c in candidates if c)}"
    )


class Renderer:
    """
    Paints screens as images.

    Frames are all the same size whatever they contain, because an animation
    whose canvas resizes is one browsers handle badly.
    """

    def __init__(
        self, cols: int = COLS, rows: int = ROWS, size: int = FONT_SIZE
    ) -> None:
        path = find_font()
        self.font = ImageFont.truetype(str(path), size)
        self.bold = self._variant(path, size)
        # The exact advance, not a rounded one: a row drawn as several runs is
        # positioned run by run, and rounding the cell width drifts the runs of a
        # styled row out of line with the borders drawn at an integer cell.
        self.cell = self.font.getlength("M")
        self.line = round(size * 1.38)
        self.cols = cols
        self.rows = rows
        self.width = round(cols * self.cell) + PADDING * 2
        self.chrome = self.line + 12
        self.height = self.chrome + rows * self.line + PADDING

    @staticmethod
    def _variant(path: Path, size: int) -> ImageFont.FreeTypeFont:
        """
        Return the bold face of a font, or the regular one when it has none.
        """
        for index in (1, 2):
            try:
                return ImageFont.truetype(str(path), size, index=index)
            except OSError:
                continue
        return ImageFont.truetype(str(path), size)

    def frame(self, rows: Sequence[Row], title: str) -> Image:
        """
        Render one screen as an image.
        """
        image = Image.new("RGB", (self.width, self.height), BACKGROUND)
        draw = ImageDraw.Draw(image)
        self._chrome(draw, title)
        for index, row in enumerate(rows):
            self._row(draw, row, self.chrome + index * self.line)
        return image

    def _chrome(self, draw: ImageDraw.ImageDraw, title: str) -> None:
        """
        Draw the title bar, so a frame read on its own still says what it is.
        """
        draw.rectangle([0, 0, self.width, self.chrome], fill=CHROME)
        draw.line([(0, self.chrome), (self.width, self.chrome)], fill=BORDER)
        radius = max(2, self.line // 6)
        centre = self.chrome // 2
        for offset, colour in (
            (-self.cell * 2, (255, 95, 86)),
            (0, (255, 189, 46)),
            (self.cell * 2, (39, 201, 63)),
        ):
            draw.ellipse(
                [
                    PADDING + offset - radius,
                    centre - radius,
                    PADDING + offset + radius,
                    centre + radius,
                ],
                fill=colour,
            )
        draw.text(
            (self.width / 2, centre),
            title,
            font=self.font,
            fill=MUTED,
            anchor="mm",
        )

    def _row(self, draw: ImageDraw.ImageDraw, row: Row, top: int) -> None:
        """
        Draw one row, a run of characters at a time.
        """
        column = 0
        for run in spans(row):
            colour = run.style.foreground or FOREGROUND
            if run.style.dim:
                colour = _blend(colour, BACKGROUND, 0.45)
            draw.text(
                (PADDING + column * self.cell, top),
                run.text,
                font=self.bold if run.style.bold else self.font,
                fill=colour,
            )
            column += len(run.text)

    def still(self, rows: Sequence[Row], title: str) -> Image:
        """
        Render a screenshot: the same window, cropped to what it holds.
        """
        used = [row for row in rows if any(cell[0] != " " for cell in row)]
        if not used:
            raise CaptureError("nothing to capture: every row of the screen is blank")
        renderer = Renderer(self.cols, len(used), FONT_SIZE)
        return renderer.frame(used, title)


def _blend(
    colour: tuple[int, int, int], towards: tuple[int, int, int], amount: float
) -> tuple[int, int, int]:
    """
    Mix a colour towards another, which is how dim text is drawn.
    """
    red, green, blue = colour
    return (
        round(red * (1 - amount) + towards[0] * amount),
        round(green * (1 - amount) + towards[1] * amount),
        round(blue * (1 - amount) + towards[2] * amount),
    )


def write_gif(frames: Sequence[Frame], path: Path, title: str) -> None:
    """
    Paint an animated capture, sharing one palette across every frame.

    A per-frame palette would make the colours flicker between frames and cost
    several times the bytes.
    """
    renderer = Renderer()
    images = [renderer.frame(frame.rows, title) for frame in frames]
    palette = _shared_palette(images, GIF_COLORS)
    quantised = [
        image.quantize(palette=palette, dither=Image.Dither.NONE) for image in images
    ]
    quantised[0].save(
        path,
        save_all=True,
        append_images=quantised[1:],
        duration=[frame.duration_ms for frame in frames],
        loop=0,
        optimize=True,
        disposal=1,
    )


def _shared_palette(images: Sequence[Image.Image], colors: int) -> Image.Image:
    """
    Derive one palette from every colour the recording uses.

    A sample of frames is tiled into a single image, so a colour that only shows
    up in the last command still gets a slot in the palette.
    """
    sample = [image.resize((image.width // 4, image.height // 4)) for image in images]
    columns = 4
    rows = (len(sample) + columns - 1) // columns
    sheet = Image.new(
        "RGB", (sample[0].width * columns, sample[0].height * rows), BACKGROUND
    )
    for index, image in enumerate(sample):
        sheet.paste(
            image, ((index % columns) * image.width, (index // columns) * image.height)
        )
    return sheet.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)


# --------------------------------------------------------------------------- #
# Recording a real session
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Command:
    """
    One line typed into the session, and how long to let it finish.
    """

    line: str
    settle: float = 0.8


DEMO_COMMANDS = (
    Command("init"),
    Command("stats"),
    Command(f"find {DEMO_QUERY}"),
    Command(f"impact {DEMO_SYMBOL} --depth 2 --limit 8", settle=1.2),
)

# The session's own prompt, as it reaches a terminal. A command is typed when
# this is the whole of the last row, which is what tells the capture the
# previous one has finished.
PROMPT = re.compile(r"^saurix\[[^\]]*\] ?>$")


def record_session(
    workdir: Path,
    commands: Sequence[Command] = DEMO_COMMANDS,
    timeout: float = 300.0,
) -> list[Frame]:
    """
    Drive the real CLI through a pseudo-terminal and record what it printed.

    The pty is the point: a pipe would make Rich drop its colour and the
    progress bar would never redraw itself, so the recording would not look like
    the terminal a reader runs the tool in.
    """
    executable = shutil.which("saurix")
    if executable is None:
        raise CaptureError(
            "the `saurix` entry point is not on PATH; run the capture with `uv run`"
        )
    screen = Screen(COLS)
    master, slave = pty.openpty()
    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
    environment = dict(
        os.environ, TERM="xterm-256color", COLUMNS=str(COLS), LINES=str(ROWS)
    )
    environment.pop("FORCE_COLOR", None)
    process = subprocess.Popen(
        [executable, "--graph", "saurix.graph.json"],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        cwd=workdir,
        env=environment,
        start_new_session=True,
    )
    os.close(slave)
    try:
        frames = _pump(master, screen, process, commands, timeout)
    finally:
        os.close(master)
        _stop(process)
    return pace(thin(dedupe(frames), MAX_FRAMES), TARGET_MS, MIN_FRAME_MS)


@dataclass
class _Typing:
    """
    What is currently being typed into the session, and when the next keystroke
    is due.
    """

    command: Command
    buffer: str = ""
    next_char: float = 0.0

    def due(self, now: float) -> bool:
        """
        Report whether the next character of the line should go out now.
        """
        return bool(self.buffer) and now >= self.next_char

    def take(self, now: float) -> str:
        """
        Return the next character, and schedule the one after it.
        """
        char, self.buffer = self.buffer[0], self.buffer[1:]
        self.next_char = now + TYPE_SECONDS
        return char

    def start(self, command: Command, now: float) -> None:
        """
        Begin typing a command, carriage return included.
        """
        self.command = command
        self.buffer = command.line + "\r"
        self.next_char = now


def _pump(
    master: int,
    screen: Screen,
    process: subprocess.Popen[bytes],
    commands: Sequence[Command],
    timeout: float,
) -> list[Frame]:
    """
    Read the session, type the commands into it, and sample the screen.

    Typing is driven by what the screen shows rather than by a guess at how long
    indexing takes: a command goes out when the prompt comes back, so the
    recording paces itself the way a person at the keyboard would.
    """
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    pending = list(commands)
    frames: list[Frame] = []
    started = time.monotonic()
    deadline = started + timeout
    last_sample = started
    typing: _Typing | None = None
    settle_until = started + 1.5

    while True:
        now = time.monotonic()
        if now > deadline:
            raise CaptureError(
                f"the session did not finish within {timeout:.0f}s; the last "
                f"{ROWS} rows it reached were:\n" + "\n".join(window(screen, ROWS))
            )
        readable, _, _ = select.select([master], [], [], 0.02)
        if readable:
            try:
                data = os.read(master, 65536)
            except OSError:
                data = b""
            if data:
                screen.feed(decoder.decode(data))

        if typing is not None and typing.due(now):
            os.write(master, typing.take(now).encode())
        elif pending and typing is None and now >= settle_until and _waiting(screen):
            typing = _Typing(pending.pop(0))
            typing.start(typing.command, now)
        elif typing is not None and not typing.buffer:
            # The line is in; give the command a moment to finish before the
            # next one is typed over its output.
            settle_until = now + typing.command.settle
            typing = None
        elif not pending and typing is None and now >= settle_until:
            # Every command has been typed and the last one has had its time.
            break

        sampled = time.monotonic()
        if sampled - last_sample >= SAMPLE_SECONDS:
            frames.append(
                Frame(
                    rows=tuple(window_rows(screen, ROWS)),
                    duration_ms=round((sampled - last_sample) * 1000),
                )
            )
            last_sample = sampled
        if process.poll() is not None and not readable:
            break

    frames.append(
        Frame(rows=tuple(window_rows(screen, ROWS)), duration_ms=MIN_FRAME_MS)
    )
    return frames


def _waiting(screen: Screen) -> bool:
    """
    Report whether the session is sitting at its prompt, ready for a command.
    """
    return bool(PROMPT.match(screen.last_line().rstrip()))


def _stop(process: subprocess.Popen[bytes]) -> None:
    """
    End the session, and anything it started, without leaving orphans.
    """
    if process.poll() is not None:
        return
    with suppress(OSError):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:  # pragma: no cover
        with suppress(OSError):
            os.killpg(process.pid, signal.SIGKILL)


# --------------------------------------------------------------------------- #
# The other two captures
# --------------------------------------------------------------------------- #


def mcp_transcript(workdir: Path, cols: int = COLS) -> Screen:
    """
    Build a screen showing real MCP calls and the responses they returned.

    The calls come from the generator that writes the committed documentation,
    so every identifier on screen is one a reader can copy out of
    `demo-mcp.md` and run. The responses are the payloads as they came back,
    cut where a screenshot has to cut them and marked where they were cut. The
    only thing rewritten is the checkout prefix in a path, which is what keeps
    the lines inside the terminal.
    """
    transcript = DEMO.run_scenario(str(workdir), str(workdir / "saurix.graph.json"))
    screen = Screen(cols)
    for line in [
        "[bold cyan]One server, eight tools.[/] Three of the calls an agent makes.",
        "[dim]Real payloads, cut where the picture cuts them.[/]",
    ]:
        _write(screen, f"\n{line}")
    for index, tool in enumerate(MCP_SHOWN, start=1):
        call = transcript.call(tool)
        arguments = json.dumps(
            {key: _trim(value, workdir) for key, value in call.arguments.items()}
        )
        _write(
            screen,
            f"\n[bold cyan]{index}. {tool}[/]"
            f"  [dim]{_shorten(arguments, cols - len(tool) - 6)}[/]",
        )
        for line in _payload_lines(call.response, workdir):
            _write(screen, f"\n{line}")
    return screen


# The calls the README's screenshot is captioned with, in the order an agent
# works out where something is defined and what a change would break. Indexing
# is left out: the recording above already shows it, and its response is the
# least interesting payload of the four.
MCP_SHOWN = ("find_symbol", "path_between", "impact_of_symbol")

# How much of each payload a screenshot can hold. The envelope opens with the
# flag and the key holding the rows, and closes with the timing, so those two
# ends are always shown and only the middle of the rows is cut.
PAYLOAD_HEAD_LINES = 3
PAYLOAD_ROW_LINES = 4
PAYLOAD_TAIL_LINES = 3


def _payload_lines(response: dict[str, Any], workdir: Path) -> list[str]:
    """
    Lay out a real response: the top of the payload, its first rows, its tail.

    Every line is the line the tool sent. Where lines are left out, a marker
    says how many, so nothing in the picture claims to be more than it is.
    """
    payload = json.dumps(_trim(response, workdir), indent=2).splitlines()
    head, tail = payload[:PAYLOAD_HEAD_LINES], payload[-PAYLOAD_TAIL_LINES:]
    rows = payload[PAYLOAD_HEAD_LINES : len(payload) - PAYLOAD_TAIL_LINES]
    if not rows:
        return [*head, *tail]
    hidden = len(rows) - PAYLOAD_ROW_LINES
    shown = rows[:PAYLOAD_ROW_LINES]
    if hidden > 0:
        shown.append(f"[dim]... {hidden} lines cut ...[/]")
    return [*head, *shown, *tail]


def _shorten(text: str, width: int) -> str:
    """
    Cut a line to the terminal width, marking that it was cut.
    """
    return text if len(text) <= width else text[: width - 1] + "…"


def _trim(value: Any, root: Path) -> Any:
    """
    Trim a recorded absolute path back to the checkout it came from.
    """
    if isinstance(value, str) and str(root) in value:
        return value.replace(f"{root}/", "").replace(str(root), ".")
    if isinstance(value, dict):
        return {key: _trim(item, root) for key, item in value.items()}
    if isinstance(value, list):
        return [_trim(item, root) for item in value]
    return value


def _write(screen: Screen, text: str) -> None:
    """
    Write a line to a screen, honouring the same markup Rich uses.

    The MCP transcript is laid out rather than recorded, but the styling on it
    comes from the same vocabulary the CLI prints with, so the two captures read
    as the same product.
    """
    for chunk, style in _style_runs(text):
        screen.write(chunk, style)


def _style_runs(text: str) -> list[tuple[str, Style]]:
    """
    Split a marked-up string into the plain runs and the style each one wears.
    """
    runs: list[tuple[str, Style]] = []
    style = Style()
    position = 0
    for match in MARKUP.finditer(text):
        if match.start() > position:
            runs.append((text[position : match.start()], style))
        if match.group(1):
            style = MARKUP_STYLES.get(match.group(1).strip(), style)
        else:
            style = Style()
        position = match.end()
    if position < len(text):
        runs.append((text[position:], style))
    return runs


def capture_dashboard(
    html: Path, out: Path, width: int = 1280, height: int = 800
) -> None:
    """
    Photograph the generated dashboard in a headless browser.

    The dashboard pulls force-graph from a CDN, so the bundle is fetched once,
    cached, and inlined into a copy of the page. That keeps the capture
    deterministic and lets it run with the network off once the bundle is there.
    """
    from playwright.sync_api import sync_playwright

    bundle = _force_graph_bundle()
    page_html = html.read_text().replace(
        "https://unpkg.com/force-graph", f"data:text/javascript;base64,{_b64(bundle)}"
    )
    staged = html.with_name("dashboard-capture.html")
    staged.write_text(page_html)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--force-color-profile=srgb"])
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(staged.resolve().as_uri())
            page.wait_for_function("() => document.querySelector('canvas') !== null")
            # The force layout needs room to settle before it is worth looking at.
            page.wait_for_timeout(4000)
            shot = page.screenshot()
        finally:
            browser.close()
    _save_png(Image.open(io.BytesIO(shot)), out)
    staged.unlink(missing_ok=True)


def _save_png(image: Image.Image, path: Path, colors: int = 128) -> None:
    """
    Write a screenshot as a paletted PNG.

    The dashboard is flat colour on a dark background, which is the worst case
    for a truecolour PNG: 128 dithered colours are indistinguishable from the
    original on screen and a third of the bytes.
    """
    image.convert("RGB").quantize(
        colors=colors,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.FLOYDSTEINBERG,
    ).save(path, optimize=True)


def _force_graph_bundle() -> bytes:
    """
    Return the pinned force-graph bundle, downloading it once.
    """
    cache = REPO_ROOT / "tmp" / "capture" / f"force-graph-{FORCE_GRAPH_VERSION}.js"
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(FORCE_GRAPH_URL) as response:  # noqa: S310
            cache.write_bytes(response.read())
    return cache.read_bytes()


def _b64(data: bytes) -> str:
    """
    Base64-encode bytes for a data URL.
    """
    import base64

    return base64.b64encode(data).decode("ascii")


# --------------------------------------------------------------------------- #
# Files
# --------------------------------------------------------------------------- #


def default_workdir() -> Path:
    """
    Return the scratch directory the session is recorded in.

    `/tmp` is used in preference to the per-user temporary directory because the
    path the CLI prints is part of the capture, and a deep one wraps every table
    the session draws.
    """
    if Path("/tmp").is_dir():
        return Path("/tmp/saurix-demo")
    return Path(os.environ.get("TEMP", "/tmp")) / "saurix-demo"  # pragma: no cover


def copy_source(source: Path, workdir: Path) -> None:
    """
    Copy a checkout to the scratch directory, minus what the capture must not
    read: scratch output, build artifacts, and any graph from a previous run.
    """
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, workdir, ignore=shutil.ignore_patterns(*COPY_IGNORES))


def image_targets(markdown: str) -> list[str]:
    """
    Return the targets of the images a markdown document shows.
    """
    return MARKDOWN_IMAGE.findall(markdown)


def asset_problems() -> list[str]:
    """
    Report the captures that are missing or have outgrown their budget.
    """
    problems: list[str] = []
    committed = 0
    for asset in ASSETS:
        path = REPO_ROOT / asset
        if not path.exists():
            problems.append(f"missing: {asset}")
            continue
        committed += path.stat().st_size
        if path.stat().st_size > ASSET_BUDGET_BYTES:
            problems.append(
                f"oversized: {asset} is {path.stat().st_size} bytes, budget is "
                f"{ASSET_BUDGET_BYTES}"
            )
    if committed > ASSET_TOTAL_BUDGET_BYTES:
        problems.append(
            f"the captures total {committed} bytes, over the budget of "
            f"{ASSET_TOTAL_BUDGET_BYTES}"
        )
    return problems


def capture(source: Path, keep: bool = False) -> list[Path]:
    """
    Take every capture, and return the files written.
    """
    workdir = default_workdir()
    copy_source(source, workdir)
    written: list[Path] = []
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    try:
        frames = record_session(workdir)
        recording = ASSET_DIR / "saurix-demo.gif"
        write_gif(frames, recording, "saurix - init, stats, find, impact")
        written.append(recording)

        cli = ASSET_DIR / "cli-workflow.png"
        Renderer().still(frames[-1].rows, "saurix - find, impact").save(
            cli, optimize=True
        )
        written.append(cli)

        # The one dashboard capture, referenced by the README and used as the
        # portfolio card image rather than shot a second time.
        card = ASSET_DIR / "visual-workflow.png"
        capture_dashboard(workdir / "saurix.html", card)
        written.append(card)

        transcript = Renderer(COLS, MCP_ROWS).still(
            window_rows(mcp_transcript(workdir), MCP_ROWS),
            "saurix-mcp - one server, eight tools",
        )
        mcp = ASSET_DIR / "mcp-workflow.png"
        transcript.save(mcp, optimize=True)
        written.append(mcp)
    finally:
        if not keep and workdir.exists():
            shutil.rmtree(workdir, ignore_errors=True)
    for path in written:
        print(f"wrote {path.relative_to(REPO_ROOT)} ({path.stat().st_size} bytes)")
    return written


def main(argv: Sequence[str] | None = None) -> int:
    """
    Capture the assets, or report the ones that have rotted.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=".",
        help="checkout to record Saurix running against (default: this one)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report on the committed captures instead of taking new ones",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="leave the scratch copy of the checkout in place for inspection",
    )
    args = parser.parse_args(argv)

    if args.check:
        problems = asset_problems()
        if problems:
            print(
                "the committed captures are not in order, run "
                "`uv run scripts/capture_demo.py`:\n"
                + "\n".join(f"  {problem}" for problem in problems),
                file=sys.stderr,
            )
            return 1
        print(f"up to date ({len(ASSETS)} captures)")
        return 0

    try:
        capture(REPO_ROOT / args.source, keep=args.keep)
    except CaptureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
