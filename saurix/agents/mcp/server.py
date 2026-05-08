from __future__ import annotations

"""MCP server setup and tool registration for Saurix."""

from . import handlers


def create_server():
    """Create FastMCP app and register all graph tooling endpoints."""
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "MCP SDK is not installed. Run `uv add mcp` or install project dependencies."
        ) from exc

    app = FastMCP("saurix")

    @app.tool()
    def index_repo(source: str, out: str | None = None) -> dict:
        """Index local path or GitHub URL into graph JSON."""
        return handlers.index_repo(source=source, out=out)

    @app.tool()
    def stats(graph: str | None = None) -> dict:
        """Return graph stats including quality and extraction coverage."""
        return handlers.stats(graph=graph)

    @app.tool()
    def find_symbol(graph: str | None, query: str, limit: int | None = None) -> dict:
        """Find symbols by fuzzy name/id match."""
        return handlers.find(graph=graph, query=query, limit=limit)

    @app.tool()
    def callers(graph: str | None, symbol: str, limit: int | None = None) -> dict:
        """List CALLS reverse edges for a symbol (who calls it)."""
        return handlers.callers(graph=graph, symbol=symbol, limit=limit)

    @app.tool()
    def callees(graph: str | None, symbol: str, limit: int | None = None) -> dict:
        """List CALLS outgoing edges for a symbol (functions it calls)."""
        return handlers.callees(graph=graph, symbol=symbol, limit=limit)

    @app.tool()
    def path_between(
        graph: str | None,
        source: str,
        target: str,
        max_depth: int | None = None,
    ) -> dict:
        """Find shortest directed path between two symbols."""
        return handlers.path_between(graph=graph, source=source, target=target, max_depth=max_depth)

    @app.tool()
    def impact_of_symbol(
        graph: str | None,
        symbol: str,
        depth: int | None = None,
        limit: int | None = None,
    ) -> dict:
        """Return reverse-neighborhood blast radius for a symbol."""
        return handlers.impact(graph=graph, symbol=symbol, depth=depth, limit=limit)

    @app.tool()
    def related_files(
        graph: str | None,
        file: str,
        depth: int | None = None,
        limit: int | None = None,
    ) -> dict:
        """List graph-neighborhood related files for one file path."""
        return handlers.related(graph=graph, file=file, depth=depth, limit=limit)

    # --- MCP Prompts (Smart Workflows) ---

    @app.prompt()
    def repo_onboarding() -> str:
        """A workflow to quickly understand a new repository's architecture."""
        return (
            "You are an expert architect. First, check if a `saurix.graph.json` exists in the current directory. "
            "If not, use the `index_repo` tool with source='.' to create one. "
            "Once indexed, use the `stats` tool to get an overview of the repo's composition. "
            "Then, use `find_symbol` to identify the main entry points or core classes, "
            "and finally explain the high-level architecture to the user."
        )

    @app.prompt()
    def analyze_change(symbol: str) -> str:
        """A workflow to assess the risk of changing a specific symbol."""
        return (
            f"I want to modify the symbol: {symbol}. "
            f"1. Use saurix `impact_of_symbol` with depth 2 to find everything that might break. "
            f"2. Use `related_files` to find which files I should check for regressions. "
            "3. Provide a summary of the 'Blast Radius' and a recommended testing strategy."
        )

    return app


def run() -> None:
    """Run MCP server over stdio transport for local agent clients."""
    create_server().run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover
    run()
