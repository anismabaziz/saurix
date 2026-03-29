from __future__ import annotations

import os
from getpass import getpass

from .commands import ShellState
from ..llm.client import DEFAULTS


def cmd_set_key(state: ShellState, rest: list[str]) -> None:
    if not rest:
        state.ui.warn("Usage: set-key <openai|anthropic|google> [api_key]")
        return

    provider = rest[0].lower()
    conf = DEFAULTS.get(provider)
    if conf is None:
        state.ui.warn("Provider must be one of: openai, anthropic, google")
        return

    key = rest[1] if len(rest) > 1 else getpass(f"Enter {provider} API key (hidden): ")
    if not key.strip():
        state.ui.warn("API key cannot be empty")
        return

    os.environ[conf.api_key_env] = key.strip()
    state.ui.success(f"Set {conf.api_key_env} for this session")


def cmd_set_provider(state: ShellState, rest: list[str]) -> None:
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
    if not rest:
        state.model = None
        state.ui.success("Model override cleared; provider default model will be used")
        return
    state.model = " ".join(rest).strip()
    state.ui.success(f"Model override set to: {state.model}")


def cmd_providers(state: ShellState) -> None:
    state.ui.header("\nAI Providers")
    for name, conf in DEFAULTS.items():
        active = " (active)" if name == state.provider else ""
        print(f"- {name}{active}")
        print(f"  default model: {conf.model}")
        print(f"  api key env : {conf.api_key_env}")


def cmd_models(state: ShellState, rest: list[str]) -> None:
    provider = (rest[0].lower() if rest else state.provider)
    if provider not in DEFAULTS:
        state.ui.warn("Usage: models [openai|anthropic|google]")
        return

    state.ui.header(f"\nModels ({provider})")
    if provider == "openai":
        print("- gpt-4o-mini")
        print("- gpt-4.1-mini")
        print("- gpt-4.1")
        print("- o4-mini")
        return

    if provider == "anthropic":
        print("- claude-3-5-haiku-latest")
        print("- claude-3-5-sonnet-latest")
        print("- claude-3-7-sonnet-latest")
        return

    print("- gemini-2.5-flash (default)")
    print("- gemini-2.5-pro")
    print("- gemini-2.0-flash")
