"""Prompt templates — per-tenant customized system prompt + intent + response.

Adapted from ShopMind-Agent src/prompts.py, modified for multi-tenant.
"""


def build_system_prompt(tenant_config: dict) -> str:
    """Build system prompt from base + tenant-specific append."""
    raise NotImplementedError("Phase 2")


def intent_prompt(user_input: str) -> str:
    """Prompt for intent classification via LLM."""
    raise NotImplementedError("Phase 2")


def response_prompt(intent: str, context: str, history: list[dict], user_input: str) -> str:
    """Prompt for generating final customer response."""
    raise NotImplementedError("Phase 2")
