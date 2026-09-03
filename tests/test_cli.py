"""Tests for the interactive CLI command surface.

Confirms the exporters cleanup: the ``export`` command is no longer dispatched
(an unknown-command warning is shown) and the interactive help no longer lists it.
"""

from __future__ import annotations

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
