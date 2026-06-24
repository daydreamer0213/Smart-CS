"""Rule + LLM hybrid intent classification — per-tenant keyword configuration.

Phase 2 implementation: rule match first, LLM fallback; keywords from tenant.config_json.
Intent labels: faq, human, unknown.
"""


def classify_intent(user_input: str, tenant_config: dict) -> tuple[str, str, float]:
    """Classify user intent. Returns (intent_label, source, confidence)."""
    raise NotImplementedError("Phase 2")


def should_handoff(intent: str, confidence: float, threshold: float) -> bool:
    """Determine if the conversation should be handed off to a human."""
    raise NotImplementedError("Phase 2")
