"""Chat pipeline orchestrator — cache -> intent -> retrieval -> LLM -> persist.

Phase 2 implementation: coordinates L1/L2 cache, intent classifier,
retrieval fusion, LLM generation, and conversation persistence.
"""


async def process_chat(tenant_id: str, session_id: str, message: str) -> dict:
    """Execute full chat pipeline for a single user message."""
    raise NotImplementedError("Phase 2")
