"""Sliding-window conversation context management.

Phase 2 implementation: trim by token count (tiktoken) and turn count.
"""


def build_context(
    history: list[dict],
    max_tokens: int = 2000,
    max_turns: int = 10,
) -> list[dict]:
    """Trim conversation history to fit within token and turn limits."""
    raise NotImplementedError("Phase 2")
