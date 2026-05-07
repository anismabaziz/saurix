# MCP Client Configs

Use these snippets to connect Code Atlas MCP server to common clients.

> [!IMPORTANT]
> Replace `/YOUR/PATH/TO/code-atlas` with the actual absolute path to this repository on your machine.

## Claude Desktop

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "code-atlas": {
      "command": "uv",
      "args": [
        "run",
        "code-atlas-mcp"
      ],
      "cwd": "/YOUR/PATH/TO/code-atlas"
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
        "code-atlas-mcp"
      ],
      "cwd": "/YOUR/PATH/TO/code-atlas"
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
    "code-atlas-mcp"
  ],
  "cwd": "/YOUR/PATH/TO/code-atlas"
}
```

---

## 🚀 Using Smart Workflows (Prompts)

Code Atlas provides "Prompts" which are pre-defined workflows for AI agents.

### How to use:
1. **In Claude Desktop**: Click the "Prompts" icon (or a spark icon) and select `repo-onboarding` or `analyze-change`.
2. **In other clients**: Simply ask the agent: *"Use the code-atlas repo-onboarding prompt"* or *"Run the analyze-change prompt for the symbol 'MyClass'"*.

These prompts guide the agent through a structured sequence of indexing, statistics gathering, and architectural analysis.
