# MCP Client Configs

Use these snippets to connect Code Atlas MCP server to common clients.

Assumption: project path is `/Users/abaziz/Documents/programming/portfolio-projects/code-atlas`.

## Claude Desktop

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "code-atlas": {
      "command": "uv",
      "args": [
        "run",
        "python",
        "-m",
        "code_atlas.mcp.server"
      ],
      "cwd": "/Users/abaziz/Documents/programming/portfolio-projects/code-atlas"
    }
  }
}
```

## Cursor

`~/.cursor/mcp.json`:

```json
{
  "servers": {
    "code-atlas": {
      "command": "uv",
      "args": [
        "run",
        "python",
        "-m",
        "code_atlas.mcp.server"
      ],
      "cwd": "/Users/abaziz/Documents/programming/portfolio-projects/code-atlas"
    }
  }
}
```

## GitHub Copilot Chat (MCP)

Example local MCP server entry:

```json
{
  "name": "code-atlas",
  "type": "stdio",
  "command": "uv",
  "args": [
    "run",
    "python",
    "-m",
    "code_atlas.mcp.server"
  ],
  "cwd": "/Users/abaziz/Documents/programming/portfolio-projects/code-atlas"
}
```

Note: exact Copilot config location/shape may vary by editor version; keep command/args/cwd the same.
