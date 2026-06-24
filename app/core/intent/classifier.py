"""Rule + LLM hybrid intent classifier — per-tenant keyword configuration."""

import structlog
from pydantic import BaseModel, Field

from app.core.llm.client import LLMClient

logger = structlog.get_logger()


class IntentOutput(BaseModel):
    intent: str = Field(..., description="faq or human")
    confidence: float = Field(..., ge=0.0, le=1.0)


async def classify_intent(
    user_input: str,
    human_keywords: list[str],
    retrieval_results: list[dict],
    llm_client: LLMClient | None = None,
    confidence_threshold: float = 0.6,
) -> tuple[str, str, float]:
    """
    Returns (intent, source, confidence)
    intent ∈ {"faq", "human"}
    source ∈ {"rule_human", "rule_faq", "llm"}
    """
    lowered = user_input.lower()

    for kw in human_keywords:
        if kw in lowered:
            logger.info("intent_rule_human", keyword=kw, input=user_input[:50])
            return ("human", "rule_human", 1.0)

    if retrieval_results:
        logger.info("intent_rule_faq", results=len(retrieval_results))
        return ("faq", "rule_faq", 0.8)

    if llm_client:
        from app.core.llm.prompts import intent_prompt
        try:
            result = await llm_client.chat_structured(
                [
                    {"role": "system", "content": "你是一个意图分类器，只返回JSON。"},
                    {"role": "user", "content": intent_prompt(user_input, human_keywords)},
                ],
                IntentOutput,
            )
            conf = float(result.confidence) if result.confidence is not None else 0.0
            if conf >= confidence_threshold:
                return (result.intent, "llm", conf)
        except Exception as e:
            logger.error("intent_llm_failed", error=str(e))

    return ("human", "llm", 0.0)
