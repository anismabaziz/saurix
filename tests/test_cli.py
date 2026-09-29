"""Tests for the interactive CLI command surface.

Confirms the exporters cleanup: the ``export`` command is no longer dispatched
(an unknown-command warning is shown) and the interactive help no longer lists it.
Also covers what the shell does with a graph file it cannot read, which is the
one thing a user hits after upgrading without re-indexing.
"""

from __future__ import annotations

import json
from pathlib import Path

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
