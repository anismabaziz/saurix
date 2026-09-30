"""
Typed MCP response envelope used by all tool handlers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class ToolError:
    """
    Structured tool error payload for machine-friendly failures.
    """

    code: str
    message: str


@dataclass
class ToolResult:
    """
    Unified success/error wrapper returned by MCP handlers.
    """

    ok: bool
    data: Any = None
    error: ToolError | None = None
    meta: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize dataclass, keeping either the data or the error, never both.
        """
        payload = asdict(self)
        if self.error is None:
            payload.pop("error", None)
        if self.meta is None:
            payload.pop("meta", None)
        if self.data is None:
            payload.pop("data", None)
        return payload
