from __future__ import annotations

"""Interactive commands for AI provider/model/key configuration."""

import os
from getpass import getpass

from .commands import ShellState
from ..llm.client import DEFAULTS


def cmd_set_key(state: ShellState, rest: list[str]) -> None:
    """Set provider API key for current process session only."""
    if not rest:
        state.ui.warn("Usage: set-key <openai|anthropic|google> [api_key]")
        return

    provider = rest[0].lower()
    conf = DEFAULTS.get(provider)
    if conf is None:
        state.ui.warn("Provider must be one of: openai, anthropic, google")
        return

    if len(rest) > 1:
        key = rest[1]
    else:
        if not state.ui.allow_blocking_input:
            state.ui.warn("Usage in TUI: set-key <provider> <api_key>")
            return
        key = getpass(f"Enter {provider} API key (hidden): ")
    if not key.strip():
        state.ui.warn("API key cannot be empty")
        return

    os.environ[conf.api_key_env] = key.strip()
    state.ui.success(f"Set {conf.api_key_env} for this session")


def cmd_set_provider(state: ShellState, rest: list[str]) -> None:
    """Switch active provider used by `ask` command."""
    if not rest:
        state.ui.warn("Usage: set-provider <openai|anthropic|google>")
        return
    provider = rest[0].lower()
    if provider not in DEFAULTS:
        state.ui.warn("Provider must be one of: openai, anthropic, google")
        return
    state.provider = provider
    if state.model is None:
        state.ui.success(f"Provider set to {provider} (model default: {DEFAULTS[provider].model})")
    else:
        state.ui.success(f"Provider set to {provider} (custom model active: {state.model})")


def cmd_set_model(state: ShellState, rest: list[str]) -> None:
    """Set explicit model override, or clear to provider default."""
    if not rest:
        state.model = None
        state.ui.success("Model override cleared; provider default model will be used")
        return
    state.model = " ".join(rest).strip()
    state.ui.success(f"Model override set to: {state.model}")


def cmd_providers(state: ShellState) -> None:
    """Print supported providers, defaults, and active one."""
    state.ui.header("\nAI Providers")
    for name, conf in DEFAULTS.items():
        active = " (active)" if name == state.provider else ""
        state.ui.print(f"- {name}{active}")
        state.ui.print(f"  default model: {conf.model}")
        state.ui.print(f"  api key env : {conf.api_key_env}")


def cmd_models(state: ShellState, rest: list[str]) -> None:
    """Print curated static model list for a provider."""
    provider = (rest[0].lower() if rest else state.provider)
    if provider not in DEFAULTS:
        state.ui.warn("Usage: models [openai|anthropic|google]")
        return

    state.ui.header(f"\nModels ({provider})")
    if provider == "openai":
        state.ui.print("- gpt-4o-mini")
        state.ui.print("- gpt-4.1-mini")
        state.ui.print("- gpt-4.1")
        state.ui.print("- o4-mini")
        return

    if provider == "anthropic":
        state.ui.print("- claude-3-5-haiku-latest")
        state.ui.print("- claude-3-5-sonnet-latest")
        state.ui.print("- claude-3-7-sonnet-latest")
        return

    state.ui.print("- gemini-2.5-flash (default)")
    state.ui.print("- gemini-2.5-pro")
    state.ui.print("- gemini-2.0-flash")
