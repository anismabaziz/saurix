from __future__ import annotations

"""Interactive `ask` command wired to graph-grounded LLM answers."""

from .commands import ShellState
from ..llm import LLMClient, build_question_context


def cmd_ask(state: ShellState, rest: list[str], provider: str, model: str | None) -> None:
    """Answer natural-language question using graph context + selected LLM."""
    if state.loaded_graph is None:
        state.ui.warn("No graph loaded. Run 'index <repo-or-github-url>' or 'load [PATH]' first.")
        return
    question = " ".join(rest).strip()
    if not question:
        state.ui.warn("Usage: ask <natural language question>")
        return

    try:
        context = build_question_context(state.loaded_graph, question)
        client = LLMClient(provider=provider, model=model)
        answer = client.answer(question, context)
    except Exception as exc:
        message = str(exc)
        if "RESOURCE_EXHAUSTED" in message or "quota" in message.lower() or "429" in message:
            state.ui.error("Ask failed: provider quota/rate limit reached.")
            if provider == "google":
                state.ui.warn("Try: set-model gemini-2.5-flash or switch provider with set-provider openai|anthropic")
            else:
                state.ui.warn("Try: switch model/provider or retry after cooldown")
            return
        state.ui.error(f"Ask failed: {message}")
        return

    state.ui.header("\nAI Answer")
    print(answer)
