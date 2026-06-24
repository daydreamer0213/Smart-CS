"""Chat pipeline orchestrator."""

import time

import structlog

from app.config import settings
from app.core.intent.classifier import classify_intent
from app.core.llm.client import LLMClient
from app.core.llm.prompts import HANDOFF_MESSAGE, build_system_prompt, response_prompt
from app.core.retrieval_module import get_bm25_manager, get_embedding_provider, get_vector_store
from app.core.retrieval.fusion import rrf_fusion
from app.schemas.chat import ChatResponse

logger = structlog.get_logger()

_llm_client: LLMClient | None = None


def _get_llm() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
    return _llm_client


async def _retrieve(tenant_slug: str, query: str) -> list[dict]:
    vs = get_vector_store()
    bm = get_bm25_manager()
    emb = get_embedding_provider()

    query_vec = (await emb.embed([query]))[0]
    vector_results = vs.search(tenant_slug, query_vec, top_k=5)
    bm25_results = bm.search(tenant_slug, query, top_k=5)

    fused = rrf_fusion(vector_results, bm25_results, top_k=5)

    # Enrich with knowledge item content
    return [
        {
            "doc_id": r["doc_id"],
            "score": r["score"],
            "sources": r["sources"],
        }
        for r in fused
    ]


async def process_chat(
    tenant_slug: str,
    tenant_name: str,
    tenant_config: dict,
    session_id: str,
    message: str,
) -> ChatResponse:
    t0 = time.monotonic()

    # Step 1: Hybrid retrieval
    retrieval_results = await _retrieve(tenant_slug, message)

    # Step 2: Intent classification
    intent, source, confidence = await classify_intent(
        user_input=message,
        human_keywords=tenant_config.get("human_keywords", []),
        retrieval_results=retrieval_results,
        llm_client=_get_llm(),
        confidence_threshold=tenant_config.get(
            "intent_threshold_override", settings.intent_confidence_threshold
        ),
    )

    # Step 3: Human handoff
    if intent == "human":
        return ChatResponse(
            answer=HANDOFF_MESSAGE,
            intent="human",
            confidence=confidence,
            sources=[],
            cache_hit="miss",
            session_id=session_id,
        )

    # Step 4: LLM generation
    llm = _get_llm()
    system_prompt = build_system_prompt(
        tenant_name,
        tenant_config.get("system_prompt_append", ""),
    )
    prompt = response_prompt(intent, retrieval_results[:3], [], message)
    answer = await llm.chat([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ])

    elapsed = (time.monotonic() - t0) * 1000
    logger.info(
        "chat_completed",
        intent=intent,
        source=source,
        results=len(retrieval_results),
        latency_ms=round(elapsed, 2),
    )

    return ChatResponse(
        answer=answer,
        intent=intent,
        confidence=confidence,
        sources=retrieval_results[:3],
        cache_hit="miss",
        session_id=session_id,
    )
