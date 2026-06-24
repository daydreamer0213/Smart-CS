"""LLM client wrapper — chat completion + embedding, with fallback chain.

Phase 2 implementation: primary DeepSeek, fallback configurable.
"""


async def chat_completion(messages: list[dict], model: str, **kwargs) -> str:
    """Send chat completion request; return response text."""
    raise NotImplementedError("Phase 2")


async def get_embedding(text: str, model: str) -> list[float]:
    """Get text embedding vector."""
    raise NotImplementedError("Phase 2")
