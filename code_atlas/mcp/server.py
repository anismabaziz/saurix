from __future__ import annotations

"""MCP server setup and tool registration for Code Atlas."""

from . import handlers


def create_server():
    """Create FastMCP app and register all graph tooling endpoints."""
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "MCP SDK is not installed. Run `uv add mcp` or install project dependencies."
        ) from exc

    app = FastMCP("code-atlas")

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
        """List CALLS reverse edges for a symbol."""
        return handlers.callers(graph=graph, symbol=symbol, limit=limit)

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

    return app


def run() -> None:
    """Run MCP server over stdio transport for local agent clients."""
    create_server().run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover
    run()
