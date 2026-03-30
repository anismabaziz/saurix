from __future__ import annotations

"""Interactive commands for AI provider/model/key configuration."""

import os
from getpass import getpass

from .commands import ShellState
from ..llm.client import DEFAULTS
from ..llm.keychain import load_api_key, save_api_key


def cmd_set_key(state: ShellState, rest: list[str]) -> None:
    """Set provider API key for session and save in keychain when available."""
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
    if save_api_key(provider, key.strip()):
        state.ui.success(f"Set {conf.api_key_env} for this session and saved in keychain")
    else:
        state.ui.success(f"Set {conf.api_key_env} for this session")
        state.ui.muted("Tip: install 'keyring' package to persist keys securely")


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


def cmd_ai_status(state: ShellState) -> None:
    """Show active provider/model and API key source without revealing secret."""
    provider = state.provider
    conf = DEFAULTS[provider]
    model = state.model or conf.model
    env_present = bool(os.getenv(conf.api_key_env))
    keychain_present = bool(load_api_key(provider))

    state.ui.header("\nAI Status")
    state.ui.print(f"- provider      : {provider}")
    state.ui.print(f"- model         : {model}")
    state.ui.print(f"- key env var   : {conf.api_key_env}")
    state.ui.print(f"- env key found : {'yes' if env_present else 'no'}")
    state.ui.print(f"- keychain found: {'yes' if keychain_present else 'no'}")

    if env_present:
        state.ui.success("Using API key from environment variable")
    elif keychain_present:
        state.ui.success("Using API key from keychain")
    else:
        state.ui.warn("No API key found. Use: set-key <provider> <api_key>")
