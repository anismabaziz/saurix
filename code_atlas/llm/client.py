from __future__ import annotations

"""Small provider-agnostic LLM client wrapper used by CLI ask command."""

import json
import os
from dataclasses import dataclass


@dataclass
class ProviderConfig:
    """Provider defaults and required API-key env var."""
    provider: str
    model: str
    api_key_env: str


DEFAULTS = {
    "openai": ProviderConfig(provider="openai", model="gpt-4o-mini", api_key_env="OPENAI_API_KEY"),
    "anthropic": ProviderConfig(provider="anthropic", model="claude-3-5-haiku-latest", api_key_env="ANTHROPIC_API_KEY"),
    "google": ProviderConfig(provider="google", model="gemini-2.5-flash", api_key_env="GOOGLE_API_KEY"),
}


class LLMClient:
    """Dispatch text generation requests to selected provider SDK."""

    def __init__(self, provider: str, model: str | None = None) -> None:
        if provider not in DEFAULTS:
            raise ValueError(f"Unsupported provider: {provider}")
        base = DEFAULTS[provider]
        self.provider = provider
        self.model = model or base.model
        self.api_key_env = base.api_key_env

    def answer(self, question: str, context: dict[str, object]) -> str:
        """Generate final answer from question + structured graph context."""
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing API key env var: {self.api_key_env}")

        if self.provider == "openai":
            return self._answer_openai(api_key, question, context)
        if self.provider == "anthropic":
            return self._answer_anthropic(api_key, question, context)
        if self.provider == "google":
            return self._answer_google(api_key, question, context)
        raise RuntimeError(f"Unsupported provider: {self.provider}")

    def classify_intent(self, question: str) -> str:
        """Classify ask intent as overview or graph using provider model."""
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing API key env var: {self.api_key_env}")

        if self.provider == "openai":
            return self._classify_intent_openai(api_key, question)
        if self.provider == "anthropic":
            return self._classify_intent_anthropic(api_key, question)
        if self.provider == "google":
            return self._classify_intent_google(api_key, question)
        raise RuntimeError(f"Unsupported provider: {self.provider}")

    def _answer_openai(self, api_key: str, question: str, context: dict[str, object]) -> str:
        """Call OpenAI chat-completions API."""
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": _system_prompt(context)},
                {"role": "user", "content": _user_prompt(question, context)},
            ],
            temperature=0.2,
        )
        return (response.choices[0].message.content or "").strip()

    def _answer_anthropic(self, api_key: str, question: str, context: dict[str, object]) -> str:
        """Call Anthropic messages API."""
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=900,
            system=_system_prompt(context),
            messages=[{"role": "user", "content": _user_prompt(question, context)}],
        )
        text_parts = [b.text for b in response.content if getattr(b, "type", "") == "text"]
        return "\n".join(text_parts).strip()

    def _answer_google(self, api_key: str, question: str, context: dict[str, object]) -> str:
        """Call Google GenAI generate_content API."""
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=self.model,
            contents=_user_prompt(question, context),
            config=types.GenerateContentConfig(
                system_instruction=_system_prompt(context),
                temperature=0.2,
            ),
        )
        return (response.text or "").strip()

    def _classify_intent_openai(self, api_key: str, question: str) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": _intent_system_prompt()},
                {"role": "user", "content": _intent_user_prompt(question)},
            ],
            temperature=0,
            max_tokens=10,
        )
        return _normalize_intent((response.choices[0].message.content or "").strip())

    def _classify_intent_anthropic(self, api_key: str, question: str) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=10,
            system=_intent_system_prompt(),
            messages=[{"role": "user", "content": _intent_user_prompt(question)}],
        )
        text_parts = [b.text for b in response.content if getattr(b, "type", "") == "text"]
        return _normalize_intent("\n".join(text_parts).strip())

    def _classify_intent_google(self, api_key: str, question: str) -> str:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=self.model,
            contents=_intent_user_prompt(question),
            config=types.GenerateContentConfig(
                system_instruction=_intent_system_prompt(),
                temperature=0,
                max_output_tokens=10,
            ),
        )
        return _normalize_intent((response.text or "").strip())


def _system_prompt(context: dict[str, object]) -> str:
    intent = str(context.get("intent", "graph"))
    if intent == "overview":
        return (
            "You are Code Atlas assistant. The user asked a high-level repository question. "
            "Answer with a concise repository overview first: what it does, main capabilities, and major modules. "
            "Use symbols/files only as supporting evidence, not as the main framing. "
            "If context is insufficient, say what is missing."
        )

    return (
        "You are Code Atlas assistant. Answer based on provided graph context only. "
        "Be concise, technical, and cite symbol IDs or files when possible. "
        "If context is insufficient, say what is missing."
    )


def _user_prompt(question: str, context: dict[str, object]) -> str:
    return (
        f"Question:\n{question}\n\n"
        "Graph Context (JSON):\n"
        f"{json.dumps(context, indent=2, sort_keys=True)}\n"
    )


def _intent_system_prompt() -> str:
    return (
        "You classify user intent for a code graph assistant. "
        "Return exactly one token: overview or graph. "
        "overview: high-level repository purpose, architecture, summary, goal, what project does. "
        "graph: symbol-level debugging/navigation like callers, impact, path, where defined."
    )


def _intent_user_prompt(question: str) -> str:
    return f"Question: {question}\nIntent token:"


def _normalize_intent(value: str) -> str:
    lowered = value.strip().lower()
    if lowered.startswith("overview"):
        return "overview"
    return "graph"
