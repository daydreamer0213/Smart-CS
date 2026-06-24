"""Chat pipeline orchestrator."""

import json
import time

import structlog
from sqlalchemy.orm import Session

from app.config import settings
from app.core.intent.classifier import classify_intent
from app.core.llm.client import LLMClient
from app.core.llm.prompts import HANDOFF_MESSAGE, build_system_prompt, response_prompt
from app.core.retrieval_module import (
    get_bm25_manager,
    get_embedding_provider,
    get_l1_cache,
    get_l2_cache,
    get_vector_store,
)
from app.core.retrieval.fusion import rrf_fusion
from app.models.tenant import Tenant
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


async def _retrieve(tenant_slug: str, query: str, db) -> list[dict]:
    vs = get_vector_store()
    bm = get_bm25_manager()
    emb = get_embedding_provider()

    query_vec = (await emb.embed([query]))[0]
    vector_results = vs.search(tenant_slug, query_vec, top_k=5)
    bm25_results = bm.search(tenant_slug, query, top_k=5)

    fused = rrf_fusion(vector_results, bm25_results, top_k=5)

    # Enrich with actual question/answer from database
    from app.models.knowledge import KnowledgeItem
    doc_ids = [r["doc_id"] for r in fused]
    items = db.query(KnowledgeItem).filter(KnowledgeItem.id.in_(doc_ids)).all() if doc_ids else []
    item_map = {item.id: item for item in items}

    return [
        {
            "doc_id": r["doc_id"],
            "score": r["score"],
            "sources": r["sources"],
            "question": item_map[r["doc_id"]].question if r["doc_id"] in item_map else "",
            "answer": item_map[r["doc_id"]].answer if r["doc_id"] in item_map else "",
        }
        for r in fused
    ]


async def process_chat(
    tenant: Tenant,
    db: Session,
    session_id: str,
    message: str,
) -> ChatResponse:
    t0 = time.monotonic()

    # ---- Step 0: L1 exact-match cache ----
    l1 = get_l1_cache()
    if l1:
        cached = l1.get(tenant.id, message)
        if cached:
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.info("chat_cache_hit", cache_hit="L1", latency_ms=round(elapsed_ms, 2))
            return ChatResponse(
                answer=cached,
                intent="faq",
                confidence=1.0,
                sources=[],
                cache_hit="L1",
                session_id=session_id,
            )

    # ---- Step 0.5: L2 semantic cache ----
    emb = get_embedding_provider()
    query_emb = (await emb.embed([message]))[0]

    l2 = get_l2_cache()
    if l2:
        cached = l2.get(tenant.id, query_emb, threshold=settings.l2_cache_threshold)
        if cached:
            if l1:
                l1.set(tenant.id, message, cached)  # promote to L1
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.info("chat_cache_hit", cache_hit="L2", latency_ms=round(elapsed_ms, 2))
            return ChatResponse(
                answer=cached,
                intent="faq",
                confidence=1.0,
                sources=[],
                cache_hit="L2",
                session_id=session_id,
            )

    # Step 1: Hybrid retrieval
    retrieval_results = await _retrieve(tenant.slug, message, db)

    # Step 2: Intent classification
    tenant_config = tenant.config_json or {}
    intent, source, confidence = await classify_intent(
        user_input=message,
        human_keywords=tenant_config.get("human_keywords", []),
        retrieval_results=retrieval_results,
        llm_client=_get_llm(),
        confidence_threshold=tenant_config.get("intent_threshold_override") or settings.intent_confidence_threshold,
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
        tenant.name,
        tenant_config.get("system_prompt_append", ""),
    )
    prompt = response_prompt(intent, retrieval_results[:3], [], message)
    answer = await llm.chat([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ])

    # ---- Step 5: Write to caches ----
    if l1:
        l1.set(tenant.id, message, answer)
    if l2:
        l2.set(tenant.id, query_emb, answer)

    elapsed = (time.monotonic() - t0) * 1000
    logger.info(
        "chat_completed",
        intent=intent,
        source=source,
        results=len(retrieval_results),
        latency_ms=round(elapsed, 2),
    )

    # ---- Step 6: Persist conversation and message ----
    from app.models.conversation import Conversation, Message

    conv = db.query(Conversation).filter(
        Conversation.tenant_id == tenant.id,
        Conversation.session_id == session_id,
    ).first()
    if conv:
        conv.message_count += 1
    else:
        conv = Conversation(tenant_id=tenant.id, session_id=session_id)
        db.add(conv)
        db.flush()

    msg = Message(
        conversation_id=conv.id,
        role="user",
        content=message,
        intent=intent,
    )
    db.add(msg)

    return ChatResponse(
        answer=answer,
        intent=intent,
        confidence=confidence,
        sources=retrieval_results[:3],
        cache_hit="miss",
        session_id=session_id,
    )


async def process_chat_stream(
    tenant: Tenant,
    db: Session,
    session_id: str,
    message: str,
):
    """Chat pipeline that yields SSE events.

    Mirrors ``process_chat`` but streams LLM tokens as ``delta`` SSE
    events and emits ``sources`` / ``done`` events so the client can
    progressively render the response.

    Event types yielded:
        sources -- hybrid retrieval results
        delta   -- incremental LLM content token
        done    -- final ChatResponse dict (or cached answer / handoff)
    """
    t0 = time.monotonic()

    # ---- Step 0: L1 exact-match cache ----
    l1 = get_l1_cache()
    if l1:
        cached = l1.get(tenant.id, message)
        if cached:
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.info("chat_stream_cache_hit", cache_hit="L1", latency_ms=round(elapsed_ms, 2))
            yield f"data: {json.dumps({'type': 'done', 'data': {'answer': cached, 'intent': 'faq', 'confidence': 1.0, 'sources': [], 'cache_hit': 'L1', 'session_id': session_id}})}\n\n"
            return

    # ---- Step 0.5: L2 semantic cache ----
    emb = get_embedding_provider()
    query_emb = (await emb.embed([message]))[0]

    l2 = get_l2_cache()
    if l2:
        cached = l2.get(tenant.id, query_emb, threshold=settings.l2_cache_threshold)
        if cached:
            if l1:
                l1.set(tenant.id, message, cached)  # promote to L1
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.info("chat_stream_cache_hit", cache_hit="L2", latency_ms=round(elapsed_ms, 2))
            yield f"data: {json.dumps({'type': 'done', 'data': {'answer': cached, 'intent': 'faq', 'confidence': 1.0, 'sources': [], 'cache_hit': 'L2', 'session_id': session_id}})}\n\n"
            return

    # Step 1: Hybrid retrieval
    retrieval_results = await _retrieve(tenant.slug, message, db)

    # Step 2: Intent classification
    tenant_config = tenant.config_json or {}
    intent, source, confidence = await classify_intent(
        user_input=message,
        human_keywords=tenant_config.get("human_keywords", []),
        retrieval_results=retrieval_results,
        llm_client=_get_llm(),
        confidence_threshold=tenant_config.get("intent_threshold_override") or settings.intent_confidence_threshold,
    )

    # Step 3: Human handoff
    if intent == "human":
        yield f"data: {json.dumps({'type': 'done', 'data': {'answer': HANDOFF_MESSAGE, 'intent': 'human', 'confidence': confidence, 'sources': [], 'cache_hit': 'miss', 'session_id': session_id}})}\n\n"
        return

    # Step 4: Build LLM prompts
    llm = _get_llm()
    system_prompt = build_system_prompt(
        tenant.name,
        tenant_config.get("system_prompt_append", ""),
    )
    prompt = response_prompt(intent, retrieval_results[:3], [], message)

    # Yield sources event before streaming starts
    yield f"data: {json.dumps({'type': 'sources', 'data': retrieval_results[:3]})}\n\n"

    # Step 5: Stream LLM tokens
    full_answer = ""
    async for token in llm.chat_stream([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]):
        full_answer += token
        yield f"data: {json.dumps({'type': 'delta', 'data': token})}\n\n"

    # ---- Step 6: Write to caches ----
    if l1:
        l1.set(tenant.id, message, full_answer)
    if l2:
        l2.set(tenant.id, query_emb, full_answer)

    elapsed = (time.monotonic() - t0) * 1000
    logger.info(
        "chat_stream_completed",
        intent=intent,
        source=source,
        results=len(retrieval_results),
        latency_ms=round(elapsed, 2),
    )

    # ---- Step 7: Persist conversation and message ----
    from app.models.conversation import Conversation, Message

    conv = db.query(Conversation).filter(
        Conversation.tenant_id == tenant.id,
        Conversation.session_id == session_id,
    ).first()
    if conv:
        conv.message_count += 1
    else:
        conv = Conversation(tenant_id=tenant.id, session_id=session_id)
        db.add(conv)
        db.flush()

    msg = Message(
        conversation_id=conv.id,
        role="user",
        content=message,
        intent=intent,
    )
    db.add(msg)

    # Yield done event with final ChatResponse data
    yield f"data: {json.dumps({'type': 'done', 'data': {'answer': full_answer, 'intent': intent, 'confidence': confidence, 'sources': retrieval_results[:3], 'cache_hit': 'miss', 'session_id': session_id}})}\n\n"
