"""Chat pipeline — LangGraph agent with chitchat / cache / streaming."""

import json
import time

import structlog
from sqlalchemy.orm import Session

from app.config import settings
from app.core.agent.graph import build_agent_graph
from app.core.agent.state import AgentState
from app.core.agent.tools import handoff_to_human, is_handoff_triggered, search_knowledge, set_runtime
from app.core.llm.prompts import build_agent_system_prompt
from app.core.retrieval_module import (
    get_embedding_provider,
    get_l1_cache,
    get_l2_cache,
)
from app.models.tenant import Tenant
from app.schemas.chat import ChatResponse

logger = structlog.get_logger()

# ---- constants ----
INTENT_FAQ = "faq"
INTENT_HUMAN = "human"
CACHE_L1 = "L1"
CACHE_L2 = "L2"
CACHE_MISS = "miss"
SSE_DONE = "done"
SSE_DELTA = "delta"
SSE_SOURCES = "sources"
SSE_TOOL_START = "tool_start"
SSE_TOOL_END = "tool_end"

# Simple greetings that don't need any API calls
_CHITCHAT_PATTERNS = {
    "你好", "在吗", "在不在", "hi", "hello", "您好", "嗨",
    "早上好", "下午好", "晚上好", "早", "晚安", "再见", "拜拜",
    "谢谢", "多谢", "thanks", "thank you", "ok", "好的",
}

_agent_graph = None


def _get_graph():
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = build_agent_graph()
    return _agent_graph


def _chitchat_reply(message: str, tenant_name: str) -> str | None:
    """Return a canned reply for pure chitchat, or None if not chitchat."""
    cleaned = message.strip().lower().rstrip("!！。.～~?？")
    if cleaned in _CHITCHAT_PATTERNS or len(cleaned) <= 1:
        return f"您好！我是{tenant_name}的智能客服，有什么可以帮助您的？"
    return None


# ---- shared helpers ----

def _sse_event(evt_type: str, data: dict) -> str:
    return f"data: {json.dumps({'type': evt_type, 'data': data})}\n\n"


def _done_data(answer: str, intent: str, cache_hit: str, session_id: str, handoff: bool = False):
    return _sse_event(SSE_DONE, {
        "answer": answer, "intent": intent, "confidence": 1.0,
        "sources": [], "cache_hit": cache_hit, "session_id": session_id, "handoff": handoff,
    })


def _build_agent_state(tenant: Tenant, session_id: str, message: str, system_prompt: str) -> AgentState:
    return {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        "tenant_id": tenant.id,
        "session_id": session_id,
        "handoff": False,
    }


def _persist_turn(db: Session, tenant_id: str, session_id: str, message: str, answer: str, handoff: bool = False):
    from app.models.conversation import Conversation, Message as MsgModel

    conv = db.query(Conversation).filter(
        Conversation.tenant_id == tenant_id,
        Conversation.session_id == session_id,
    ).first()
    if conv:
        conv.message_count = (conv.message_count or 0) + 1
        if handoff:
            conv.status = "handed_off"
    else:
        conv = Conversation(
            tenant_id=tenant_id, session_id=session_id,
            status="handed_off" if handoff else "active",
        )
        db.add(conv)
        db.flush()
    db.add(MsgModel(conversation_id=conv.id, role="user", content=message))
    db.add(MsgModel(conversation_id=conv.id, role="assistant", content=answer))
    db.commit()


def _write_caches(tenant_id: str, message: str, query_emb: list[float] | None, answer: str):
    if not answer:
        return
    l1 = get_l1_cache()
    l2 = get_l2_cache()
    if l1:
        l1.set(tenant_id, message, answer)
    if l2 and query_emb:
        l2.set(tenant_id, query_emb, answer)


def _extract_sources(messages: list) -> list[dict]:
    for m in messages:
        if hasattr(m, "type") and m.type == "tool" and getattr(m, "name", "") == search_knowledge.name:
            try:
                return json.loads(str(m.content)).get("results", [])
            except (json.JSONDecodeError, TypeError):
                pass
    return []


def _extract_answer(messages: list) -> str:
    for m in reversed(messages):
        if hasattr(m, "type") and m.type == "ai" and m.content:
            return m.content
        elif isinstance(m, dict) and m.get("role") == "assistant" and m.get("content"):
            return m["content"]
    return ""


async def _check_cache_and_embed(tenant_id: str, message: str) -> tuple[str | None, str, list[float]]:
    """Check L1, then L2 cache. Returns (answer_or_none, cache_hit_level, query_emb)."""
    l1 = get_l1_cache()
    if l1:
        cached = l1.get(tenant_id, message)
        if cached:
            return cached, CACHE_L1, []

    emb = get_embedding_provider()
    query_emb = (await emb.embed([message]))[0]

    l2 = get_l2_cache()
    if l2:
        cached = l2.get(tenant_id, query_emb, threshold=settings.l2_cache_threshold)
        if cached:
            if l1:
                l1.set(tenant_id, message, cached)  # promote to L1
            return cached, CACHE_L2, query_emb

    return None, CACHE_MISS, query_emb


def _agent_setup(tenant: Tenant, db: Session) -> tuple[str, dict]:
    """Build system prompt and graph config for the current tenant."""
    tenant_config = tenant.config_json or {}
    system_prompt = build_agent_system_prompt(
        tenant.name,
        tenant_config.get("system_prompt_append", ""),
    )
    set_runtime(tenant.slug, db)
    return system_prompt, {
        "configurable": {"thread_id": ""},
        "recursion_limit": settings.agent_recursion_limit,
    }


# ---- public API ----

async def process_chat(
    tenant: Tenant,
    db: Session,
    session_id: str,
    message: str,
) -> ChatResponse:
    """Non-streaming chat."""
    t0 = time.monotonic()

    cr = _chitchat_reply(message, tenant.name)
    if cr:
        return ChatResponse(answer=cr, intent=INTENT_FAQ, confidence=1.0,
                            sources=[], cache_hit=CACHE_L1, session_id=session_id)

    answer, cache_hit, query_emb = await _check_cache_and_embed(tenant.id, message)
    if answer:
        elapsed = (time.monotonic() - t0) * 1000
        logger.info("chat_cache_hit", cache_hit=cache_hit, latency_ms=round(elapsed, 2))
        return ChatResponse(answer=answer, intent=INTENT_FAQ, confidence=1.0,
                            sources=[], cache_hit=cache_hit, session_id=session_id)

    return await _run_agent(tenant, db, session_id, message, query_emb, t0)


async def _run_agent(
    tenant: Tenant, db: Session, session_id: str, message: str,
    query_emb: list[float], t0: float,
) -> ChatResponse:
    system_prompt, config = _agent_setup(tenant, db)
    config["configurable"]["thread_id"] = session_id

    graph = _get_graph()
    state = await graph.ainvoke(
        _build_agent_state(tenant, session_id, message, system_prompt),
        config,
    )

    messages = state.get("messages", [])
    answer = _extract_answer(messages)
    sources = _extract_sources(messages)
    handoff = is_handoff_triggered()

    _persist_turn(db, tenant.id, session_id, message, answer, handoff)
    _write_caches(tenant.id, message, query_emb, answer)

    elapsed = (time.monotonic() - t0) * 1000
    logger.info("agent_completed", latency_ms=round(elapsed, 2), handoff=handoff)

    return ChatResponse(
        answer=answer,
        intent=INTENT_HUMAN if handoff else INTENT_FAQ,
        confidence=1.0,
        sources=sources,
        cache_hit=CACHE_MISS,
        session_id=session_id,
        handoff=handoff,
    )


async def process_chat_stream(
    tenant: Tenant,
    db: Session,
    session_id: str,
    message: str,
):
    """Streaming chat — yields SSE events."""
    t0 = time.monotonic()

    # Fast path 0: chitchat
    cr = _chitchat_reply(message, tenant.name)
    if cr:
        logger.info("chat_chitchat", message=message)
        yield _done_data(cr, INTENT_FAQ, CACHE_L1, session_id)
        return

    # Fast path 1+2: L1 / L2 cache
    answer, cache_hit, query_emb = await _check_cache_and_embed(tenant.id, message)
    if answer:
        elapsed = (time.monotonic() - t0) * 1000
        logger.info("chat_stream_cache_hit", cache_hit=cache_hit, latency_ms=round(elapsed, 2))
        yield _done_data(answer, INTENT_FAQ, cache_hit, session_id)
        return

    # Agent path
    system_prompt, config = _agent_setup(tenant, db)
    config["configurable"]["thread_id"] = session_id

    graph = _get_graph()
    full_answer = ""
    handoff = False

    async for event in graph.astream_events(
        _build_agent_state(tenant, session_id, message, system_prompt),
        config, version="v2",
    ):
        kind = event.get("event", "")

        if kind == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and chunk.content:
                full_answer += chunk.content
                yield _sse_event(SSE_DELTA, chunk.content)

        elif kind == "on_tool_start":
            tool_name = event.get("name", "")
            yield _sse_event(SSE_TOOL_START, {"tool": tool_name})
            if tool_name == handoff_to_human.name:
                handoff = True

        elif kind == "on_tool_end":
            tool_name = event.get("name", "")
            tool_output = event.get("data", {}).get("output", "")
            if tool_name == search_knowledge.name:
                try:
                    sources_data = json.loads(str(tool_output)).get("results", [])
                except (json.JSONDecodeError, TypeError):
                    sources_data = []
                yield _sse_event(SSE_SOURCES, sources_data)

    _persist_turn(db, tenant.id, session_id, message, full_answer, handoff)
    _write_caches(tenant.id, message, query_emb, full_answer)

    elapsed = (time.monotonic() - t0) * 1000
    logger.info("agent_stream_completed", latency_ms=round(elapsed, 2), handoff=handoff)

    yield _done_data(full_answer, INTENT_HUMAN if handoff else INTENT_FAQ, CACHE_MISS, session_id, handoff)
