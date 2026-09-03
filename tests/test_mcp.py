"""Tests for the MCP server surface (tools, prompts).

Confirms the deletions from the exporters/prompts cleanup: the server keeps the
expected set of tools with compatible shapes and exposes no bundled prompts.
"""

from __future__ import annotations

import asyncio

from saurix.agents.mcp.server import create_server

EXPECTED_TOOLS = {
    "index_repo",
    "stats",
    "find_symbol",
    "callers",
    "callees",
    "path_between",
    "impact_of_symbol",
    "related_files",
}


class TestMcpTools:
    """
    The server exposes the core tool set with the same names.
    """

    def test_exposes_expected_tools(self) -> None:
        """
        The registered tool list matches the eight core tools.
        """
        app = create_server()
        tools = {t.name for t in asyncio.run(app.list_tools())}
        assert tools == EXPECTED_TOOLS


class TestNoPrompts:
    """
    The server no longer bundles onboarding or change-analysis prompts.
    """

    def test_no_prompts_registered(self) -> None:
        """
        create_server registers zero prompts.
        """
        app = create_server()
        prompts = asyncio.run(app.list_prompts())
        assert prompts == []
