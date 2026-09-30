"""
Tests for the demo capture script.

The capture runs a real session and paints frames, and neither is worth a test
run on every commit. What is worth holding is the pure part underneath: the
terminal emulation that turns a byte stream into screens, the pacing that
decides how long each frame is on screen, and the contract the committed assets
have to keep. Those are pinned here; the browser and the subprocess are not.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

CAPTURE_PATH = REPO_ROOT / "scripts" / "capture_demo.py"

# The dashboard capture is the portfolio card image, so it is captured once and
# referenced from both places rather than shot twice.
CARD_IMAGE = "docs/assets/visual-workflow.png"

# What the first screen of the README promises, spelled out here so the promise
# is checked against the repository rather than against the script that fills it.
EXPECTED_ASSETS = (
    "docs/assets/cli-workflow.png",
    "docs/assets/mcp-workflow.png",
    "docs/assets/saurix-demo.gif",
    "docs/assets/visual-workflow.png",
)


def _load_capture() -> ModuleType:
    """
    Import the capture script, which lives in scripts/ and is not a package.
    """
    spec = importlib.util.spec_from_file_location("capture_demo", CAPTURE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def capture() -> ModuleType:
    """
    Provide the capture script as a module.
    """
    return _load_capture()


class TestPalette:
    """
    The 256-colour table is derived, not copied, so a wrong entry is a wrong
    colour in the middle of the recording rather than a crash.
    """

    def test_base_colours_match_the_ansi_sixteen(self, capture: ModuleType) -> None:
        """
        The first sixteen entries are the standard ANSI colours.
        """
        assert capture.xterm256(0) == (0, 0, 0)
        assert capture.xterm256(1) == (128, 0, 0)
        assert capture.xterm256(7) == (192, 192, 192)
        assert capture.xterm256(15) == (255, 255, 255)

    def test_cube_entries_are_derived_from_their_position(
        self, capture: ModuleType
    ) -> None:
        """
        Index 196 is the first cube entry at full red, 21 the last at full blue.
        """
        assert capture.xterm256(196) == (255, 0, 0)
        assert capture.xterm256(46) == (0, 255, 0)
        assert capture.xterm256(21) == (0, 0, 255)

    def test_greyscale_ramp_runs_from_dark_to_light(self, capture: ModuleType) -> None:
        """
        The 24-step ramp starts near black and ends near white.
        """
        assert capture.xterm256(232) == (8, 8, 8)
        assert capture.xterm256(255) == (238, 238, 238)
        assert capture.xterm256(232)[0] < capture.xterm256(255)[0]

    def test_bright_range_is_the_base_range_lightened(
        self, capture: ModuleType
    ) -> None:
        """
        Index 9 is the dim red that index 1 brightens.
        """
        assert capture.xterm256(9) != capture.xterm256(1)
        assert capture.xterm256(9)[0] > capture.xterm256(1)[0]

    @pytest.mark.parametrize("index", [0, 15, 100, 231, 232, 255])
    def test_every_entry_is_a_full_colour(
        self, capture: ModuleType, index: int
    ) -> None:
        """
        No index returns a partial tuple.
        """
        assert len(capture.xterm256(index)) == 3
        assert all(0 <= channel <= 255 for channel in capture.xterm256(index))


class TestScreen:
    """
    A screen is fed whatever the child process wrote, escape codes and all, and
    has to end up holding what a terminal would show.
    """

    def test_newlines_start_new_rows(self, capture: ModuleType) -> None:
        """
        A line feed moves down rather than overwriting.
        """
        screen = capture.Screen(cols=20)
        screen.feed("one\ntwo\n")
        assert screen.text() == "one\ntwo"

    def test_carriage_return_overwrites_in_place(self, capture: ModuleType) -> None:
        """
        A progress bar redraws itself by returning to column zero, so a carriage
        return has to overwrite the row it is on.
        """
        screen = capture.Screen(cols=20)
        screen.feed("10%\r55%\r")
        assert screen.text() == "55%"

    def test_a_line_longer_than_the_terminal_wraps(self, capture: ModuleType) -> None:
        """
        Output longer than the terminal continues on the next row, as it would
        on a real one.
        """
        screen = capture.Screen(cols=4)
        screen.feed("abcdefghij")
        assert screen.text() == "abcd\nefgh\nij"

    def test_a_full_row_does_not_move_on_until_something_is_written(
        self, capture: ModuleType
    ) -> None:
        """
        Rich redraws a full-width progress line with a carriage return, so the row
        has to still be the current one for that to land on it.
        """
        screen = capture.Screen(cols=4)
        screen.feed("abcd")
        screen.feed("\rxy")
        assert screen.text() == "xycd"

    def test_sgr_sets_the_foreground(self, capture: ModuleType) -> None:
        """
        A colour code applies to the characters that follow it.
        """
        screen = capture.Screen(cols=20)
        screen.feed("\x1b[31mred\x1b[0m plain")
        assert screen.text() == "red plain"
        assert capture.style_of(screen, 0, 0).foreground == capture.xterm256(1)
        assert capture.style_of(screen, 0, 4).foreground is None

    def test_bold_and_dim_are_tracked_and_cleared(self, capture: ModuleType) -> None:
        """
        Weight attributes come and go with the code that sets them.
        """
        screen = capture.Screen(cols=20)
        screen.feed("\x1b[1;2mboth\x1b[22mplain")
        first = capture.style_of(screen, 0, 0)
        assert (first.bold, first.dim) == (True, True)
        assert (
            capture.style_of(screen, 0, 6).bold,
            capture.style_of(screen, 0, 6).dim,
        ) == (
            False,
            False,
        )

    def test_indexed_and_truecolor_both_resolve(self, capture: ModuleType) -> None:
        """
        Rich emits 256-colour codes on a pty and truecolour ones on a modern
        terminal, so both forms have to land on a colour.
        """
        screen = capture.Screen(cols=20)
        screen.feed("\x1b[38;5;196ma\x1b[0m\x1b[38;2;1;2;3mb")
        assert capture.style_of(screen, 0, 0).foreground == (255, 0, 0)
        assert capture.style_of(screen, 0, 1).foreground == (1, 2, 3)

    def test_unknown_escape_sequences_are_ignored(self, capture: ModuleType) -> None:
        """
        Rich moves the cursor and clears regions the recording never emulates;
        those sequences must not turn into visible characters.
        """
        screen = capture.Screen(cols=20)
        screen.feed("kept\x1b[K\x1b[1A\x1b[?25l\x1b[6n")
        assert screen.text() == "kept"

    def test_an_escape_split_across_two_reads_is_still_one_sequence(
        self, capture: ModuleType
    ) -> None:
        """
        A read from the child can end mid-sequence. Printing the fragment would
        put `[2m` on the recording instead of dimming the text that follows.
        """
        screen = capture.Screen(cols=20)
        screen.feed("a\x1b[2")
        screen.feed("mb")
        assert screen.text() == "ab"
        assert capture.style_of(screen, 0, 0).dim is False
        assert capture.style_of(screen, 0, 1).dim is True

    def test_rows_hold_cells_and_styled_spans_survive_a_reset(
        self, capture: ModuleType
    ) -> None:
        """
        A span is a run of same-styled cells, which is what the renderer draws.
        """
        screen = capture.Screen(cols=20)
        screen.feed("\x1b[1;31mab\x1b[0mc")
        spans = capture.spans(screen.rows()[0])
        assert [span.text for span in spans] == ["ab", "c"]

    def test_window_keeps_the_last_rows_a_reader_needs(
        self, capture: ModuleType
    ) -> None:
        """
        A session is longer than a window, so the window is the tail of it.
        """
        screen = capture.Screen(cols=20)
        screen.feed("1\n2\n3\n4\n5\n")
        assert capture.window(screen, 2) == ["4", "5"]

    def test_window_drops_the_blank_rows_a_cleared_screen_leaves(
        self, capture: ModuleType
    ) -> None:
        """
        Trailing empty rows are padding, not content, and shrink the window.
        """
        screen = capture.Screen(cols=20)
        screen.feed("only\n\n\n")
        assert capture.window(screen, 5) == ["only"]

    def test_empty_screen_has_an_empty_window(self, capture: ModuleType) -> None:
        """
        A capture that has not read anything yet is blank, not one empty row.
        """
        assert capture.window(capture.Screen(cols=20), 5) == []


class TestPace:
    """
    A recording is a real run, so its raw frame timings are as long as indexing
    took. Pacing is what turns that into something a stranger watches.
    """

    def _frames(self, capture: ModuleType, durations: list[int]) -> list:
        """
        Build frames of the given real durations, each holding a unique row.
        """
        return [
            capture.Frame(rows=(((str(index), capture.Style()),),), duration_ms=ms)
            for index, ms in enumerate(durations)
        ]

    def test_total_playback_lands_on_the_target(self, capture: ModuleType) -> None:
        """
        A minute of indexing becomes the length the reader will sit through.
        """
        frames = self._frames(capture, [10, 20, 30, 5000, 9000])
        paced = capture.pace(frames, target_ms=6000, min_ms=80)
        assert 5000 <= sum(frame.duration_ms for frame in paced) <= 6400

    def test_no_frame_is_shorter_than_the_floor(self, capture: ModuleType) -> None:
        """
        A frame that flashes past is dead time in the other direction.
        """
        frames = self._frames(capture, [1] * 40 + [60000])
        paced = capture.pace(frames, target_ms=4000, min_ms=90)
        assert all(frame.duration_ms >= 90 for frame in paced)

    def test_a_long_wait_still_gets_the_longer_share(self, capture: ModuleType) -> None:
        """
        Proportion survives the rescale: the pause stays the pause.
        """
        frames = self._frames(capture, [1000, 3000])
        paced = capture.pace(frames, target_ms=8000, min_ms=80)
        assert paced[1].duration_ms > 2 * paced[0].duration_ms

    def test_frame_count_and_content_are_untouched(self, capture: ModuleType) -> None:
        """
        Pacing rewrites timings only, and leaves the input frames alone.
        """
        frames = self._frames(capture, [500, 500, 500])
        paced = capture.pace(frames, target_ms=3000, min_ms=80)
        assert [frame.rows for frame in paced] == [frame.rows for frame in frames]
        assert [frame.duration_ms for frame in frames] == [500, 500, 500]

    def test_an_empty_capture_paces_to_nothing(self, capture: ModuleType) -> None:
        """
        No frames in means no frames out, rather than a division by zero.
        """
        assert capture.pace([], target_ms=6000, min_ms=80) == []


class TestTimeline:
    """
    The recorder samples a real run; sampling produces frames that show nothing
    new, and those are the ones that make a recording feel long.
    """

    def test_unchanged_samples_are_dropped(self, capture: ModuleType) -> None:
        """
        Consecutive identical screens collapse into one frame.
        """
        first = capture.Frame(rows=((("a", capture.Style()),),), duration_ms=50)
        same = capture.Frame(rows=((("a", capture.Style()),),), duration_ms=50)
        other = capture.Frame(rows=((("b", capture.Style()),),), duration_ms=50)
        kept = capture.dedupe([first, same, other])
        assert [frame.rows for frame in kept] == [first.rows, other.rows]

    def test_the_dropped_time_moves_to_the_frame_that_stayed(
        self, capture: ModuleType
    ) -> None:
        """
        Collapsing frames must not shorten the recording.
        """
        first = capture.Frame(rows=((("a", capture.Style()),),), duration_ms=50)
        same = capture.Frame(rows=((("a", capture.Style()),),), duration_ms=90)
        kept = capture.dedupe([first, same])
        assert kept[0].duration_ms == 140

    def test_the_last_screen_is_always_kept(self, capture: ModuleType) -> None:
        """
        A still is taken from the final frame, so it cannot be the one dropped.
        """
        first = capture.Frame(rows=((("a", capture.Style()),),), duration_ms=50)
        same = capture.Frame(rows=((("a", capture.Style()),),), duration_ms=50)
        assert capture.dedupe([first, same])[-1].rows == first.rows

    def test_a_long_capture_is_thinned_to_the_frame_budget(
        self, capture: ModuleType
    ) -> None:
        """
        More frames than a browser will decode smoothly get sampled down, which
        is also what keeps the GIF from outweighing the repository.
        """
        frames = [
            capture.Frame(rows=(((str(index), capture.Style()),),), duration_ms=50)
            for index in range(500)
        ]
        thinned = capture.thin(frames, limit=120)
        assert len(thinned) == 120
        assert thinned[0].rows == frames[0].rows
        assert thinned[-1].rows == frames[-1].rows
        # Each kept frame carries the time of the frames it stands in for, and
        # the last one carries all of it, so nothing is cut from the playback.
        assert thinned[-1].duration_ms == sum(frame.duration_ms for frame in frames)

    def test_thinning_leaves_a_capture_within_budget_alone(
        self, capture: ModuleType
    ) -> None:
        """
        No frames are invented or removed when the capture already fits.
        """
        frames = [
            capture.Frame(rows=(((str(index), capture.Style()),),), duration_ms=50)
            for index in range(10)
        ]
        assert capture.thin(frames, limit=120) == frames


class TestMarkdownImages:
    """
    The committed assets are referenced from the README by markdown image link.
    A capture that renames a file has to be caught here rather than by a reader
    looking at a broken image.
    """

    def test_image_targets_are_extracted(self, capture: ModuleType) -> None:
        """
        Both the recording and the screenshots come back.
        """
        markdown = "![a](docs/assets/one.png)\n![b](docs/assets/two.gif)\n"
        assert capture.image_targets(markdown) == [
            "docs/assets/one.png",
            "docs/assets/two.gif",
        ]

    def test_non_image_links_are_left_alone(self, capture: ModuleType) -> None:
        """
        Ordinary hyperlinks and shields are not captures and are not checked.
        """
        markdown = "[text](docs/accuracy.md)\n![shield](https://img.shields.io/x.svg)\n"
        assert capture.image_targets(markdown) == ["https://img.shields.io/x.svg"]

    def test_a_reference_with_a_title_is_still_a_reference(
        self, capture: ModuleType
    ) -> None:
        """
        Markdown allows a quoted title after the target.
        """
        assert capture.image_targets('![a](docs/assets/one.png "Title")') == [
            "docs/assets/one.png"
        ]


class TestCommittedAssets:
    """
    The repository promises a recording and three screenshots. These checks are
    what keep that promise from quietly rotting.
    """

    def test_every_image_the_readme_shows_exists(self, capture: ModuleType) -> None:
        """
        Each referenced capture is committed at the path the README names.
        """
        markdown = (REPO_ROOT / "README.md").read_text()
        missing = sorted(
            target
            for target in capture.image_targets(markdown)
            if not target.startswith("http") and not (REPO_ROOT / target).exists()
        )
        assert not missing, (
            f"README references captures that are not committed: {missing}"
        )

    @pytest.mark.parametrize("asset", EXPECTED_ASSETS)
    def test_the_readme_shows_the_capture(
        self, capture: ModuleType, asset: str
    ) -> None:
        """
        The first screen is the recording plus the CLI, dashboard, and agent
        shots. The list is spelled out in this file rather than read back from
        the script, so renaming an asset without showing it fails here.
        """
        targets = capture.image_targets((REPO_ROOT / "README.md").read_text())
        assert asset in targets, f"{asset} is not shown in the README"

    def test_the_script_publishes_every_asset_path_it_names(
        self, capture: ModuleType
    ) -> None:
        """
        The dashboard shot doubles as the portfolio card image, so the only
        asset path the script may name is one it also publishes in `ASSETS`.
        A second name for the same screenshot is the duplicate this rules out.
        """
        named = set(
            re.findall(
                r"docs/assets/[A-Za-z0-9._-]+\.(?:png|gif)", CAPTURE_PATH.read_text()
            )
        )
        undeclared = sorted(named - set(capture.ASSETS))
        assert not undeclared, (
            f"the capture script names asset paths it does not publish: {undeclared}"
        )
        assert CARD_IMAGE in capture.ASSETS

    def test_the_capture_script_documents_how_to_regenerate_the_assets(
        self, capture: ModuleType
    ) -> None:
        """
        Reproducibility is only real if the command is written down where a
        reader will look for it.
        """
        readme = (REPO_ROOT / "README.md").read_text()
        assert "scripts/capture_demo.py" in readme
        assert (REPO_ROOT / "docs" / "assets" / "README.md").exists()

    @pytest.mark.parametrize("asset", EXPECTED_ASSETS)
    def test_committed_assets_stay_small(self, capture: ModuleType, asset: str) -> None:
        """
        A capture that is allowed to grow without limit turns a half-megabyte
        repository into a slow clone.
        """
        path = REPO_ROOT / asset
        if not path.exists():
            pytest.skip(f"{asset} has not been captured yet")
        assert path.stat().st_size <= capture.ASSET_BUDGET_BYTES, (
            f"{asset} is {path.stat().st_size} bytes, over the "
            f"{capture.ASSET_BUDGET_BYTES} byte budget"
        )

    def test_the_captured_set_stays_small(self, capture: ModuleType) -> None:
        """
        Four files each under a budget can still add up to something a clone
        pays for, so the set has a budget of its own.
        """
        committed = [
            (REPO_ROOT / asset).stat().st_size
            for asset in EXPECTED_ASSETS
            if (REPO_ROOT / asset).exists()
        ]
        assert sum(committed) <= capture.ASSET_TOTAL_BUDGET_BYTES, (
            f"the captures total {sum(committed)} bytes, over the "
            f"{capture.ASSET_TOTAL_BUDGET_BYTES} byte budget"
        )
