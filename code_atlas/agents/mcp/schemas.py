from __future__ import annotations

"""Typed MCP response envelope used by all tool handlers."""

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class ToolError:
    """Structured tool error payload for machine-friendly failures."""
    code: str
    message: str


@dataclass
class ToolResult:
    """Unified success/error wrapper returned by MCP handlers."""
    ok: bool
    data: Any = None
    error: ToolError | None = None
    meta: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize dataclass and drop optional empty fields."""
        payload = asdict(self)
        if self.error is None:
            payload.pop("error", None)
        if self.meta is None:
            payload.pop("meta", None)
        return payload
