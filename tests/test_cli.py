"""Tests for the interactive CLI command surface.

Confirms the exporters cleanup: the ``export`` command is no longer dispatched
(an unknown-command warning is shown) and the interactive help no longer lists it.
Also covers what the shell does with a graph file it cannot read, which is the
one thing a user hits after upgrading without re-indexing.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from rich.console import Console

from saurix.cli.app import create_state, dispatch_command
from saurix.cli.ui import UI, interactive_help


def _render(value: object) -> str:
    """
    Flatten a rich renderable emitted to the UI sink into plain text.
    """
    return value.plain if hasattr(value, "plain") else str(value)


class TestExportRemoved:
    """
    The previously bundled ``export`` command is gone.
    """

    def test_export_is_not_a_known_command(self) -> None:
        """
        Dispatching ``export`` falls through to the unknown-command warning.
        """
        sink: list[object] = []
        ui = UI(sink=sink.append)
        state = create_state(Path("nonexistent.graph.json"), ui)
        dispatch_command(state, "export graphml")
        assert any("Unknown command" in _render(item) for item in sink)

    def test_export_not_listed_in_help(self) -> None:
        """
        Interactive help no longer mentions the export command.
        """
        help_text = interactive_help().lower()
        assert "export" not in help_text
        assert "graphml" not in help_text
        assert "neo4j" not in help_text


class TestIncrementalReporting:
    """
    The index command tells the user how much work the cache saved.
    """

    def _index(self, repo: Path, out: Path) -> list[object]:
        """
        Run the index command once and return everything it printed.
        """
        sink: list[object] = []
        ui = UI(sink=sink.append)
        state = create_state(Path("nonexistent.graph.json"), ui)
        dispatch_command(state, f"index {repo} --out {out}")
        return sink

    def test_second_run_reports_reused_files(self, tmp_path: Path) -> None:
        """
        Re-indexing an unchanged checkout reports reused file counts.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "a.py").write_text("def f():\n    return 1\n")
        out = tmp_path / "graph.json"
        self._index(repo, out)

        sink = self._index(repo, out)
        text = " ".join(_render(item) for item in sink).lower()

        assert "reused" in text
        assert "re-extracted" in text

    def test_first_run_reports_no_reuse(self, tmp_path: Path) -> None:
        """
        A first run reports that nothing was reused.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "a.py").write_text("def f():\n    return 1\n")

        sink = self._index(repo, tmp_path / "graph.json")
        text = " ".join(_render(item) for item in sink).lower()

        assert "reused 0" in text


class TestUnreadableGraph:
    """
    A graph file the loader refuses is reported, not raised.
    """

    def _stale_graph(self, tmp_path: Path) -> Path:
        """
        Write a graph in the shape 0.2.0 shipped, which 0.3.0 refuses to read.
        """
        path = tmp_path / "stale.graph.json"
        path.write_text(json.dumps({"schema_version": "1.0.0", "nodes": []}))
        return path

    def test_shell_starts_without_a_graph_it_cannot_read(self, tmp_path: Path) -> None:
        """
        Opening the shell on a stale graph leaves it unloaded and says why,
        rather than dying with a traceback before the prompt appears.
        """
        sink: list[object] = []
        state = create_state(self._stale_graph(tmp_path), UI(sink=sink.append))
        assert state.loaded_graph is None
        assert any("Re-index" in _render(item) for item in sink)

    def test_load_reports_a_graph_it_cannot_read(self, tmp_path: Path) -> None:
        """
        `load` on a stale graph reports the failure and keeps the shell usable.
        """
        path = self._stale_graph(tmp_path)
        sink: list[object] = []
        state = create_state(Path("nonexistent.graph.json"), UI(sink=sink.append))
        dispatch_command(state, f"load {path}")
        assert state.loaded_graph is None
        assert any("Re-index" in _render(item) for item in sink)


class TestMarkup:
    """
    Rich markup is only markup where the text goes through the console parser.
    A string built as a `Text` is printed literally, brackets and all, which is
    how two things used to reach the screen: the graph name in the prompt, and
    the trailer `init` ends on.
    """

    def test_prompt_names_the_graph_it_loaded(self) -> None:
        """
        The prompt says which graph is loaded. Unescaped, the markup parser
        reads the name as a style tag and the whole thing disappears.
        """
        console = Console(file=io.StringIO(), width=120)
        ui = UI(console=console)
        ui.print(ui.prompt("saurix.graph.json"))
        assert "saurix.graph.json" in console.file.getvalue()

    def test_init_trailer_shows_the_dashboard_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        `init` ends by pointing at the dashboard it wrote, and the path is
        readable rather than a `[bold]` tag left in the output.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "a.py").write_text("def f():\n    return 1\n")
        monkeypatch.chdir(repo)
        console = Console(file=io.StringIO(), width=120)
        state = create_state(repo / "saurix.graph.json", UI(console=console))

        with console.capture() as capture:
            dispatch_command(state, "init")

        printed = capture.get()
        assert "[bold]" not in printed
        assert "saurix.html" in printed
