"""Chat pipeline — now driven by the LangGraph agent.

The non-streaming ``process_chat`` and streaming ``process_chat_stream``
both check L1/L2 cache first, then delegate to the agent graph.
"""

import json
import time

import structlog
from sqlalchemy.orm import Session

from app.config import settings
from app.core.agent.graph import build_agent_graph
from app.core.agent.state import AgentState
from app.core.agent.tools import is_handoff_triggered, set_runtime
from app.core.llm.prompts import build_agent_system_prompt
from app.core.retrieval_module import (
    get_embedding_provider,
    get_l1_cache,
    get_l2_cache,
)
from app.models.tenant import Tenant
from app.schemas.chat import ChatResponse

logger = structlog.get_logger()

_agent_graph = None


def _get_graph():
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = build_agent_graph()
    return _agent_graph


async def process_chat(
    tenant: Tenant,
    db: Session,
    session_id: str,
    message: str,
) -> ChatResponse:
    """Non-streaming chat — cache check then agent invocation."""
    t0 = time.monotonic()

    # Fast path: L1 exact cache
    l1 = get_l1_cache()
    if l1:
        cached = l1.get(tenant.id, message)
        if cached:
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.info("chat_cache_hit", cache_hit="L1", latency_ms=round(elapsed_ms, 2))
            return ChatResponse(
                answer=cached, intent="faq", confidence=1.0,
                sources=[], cache_hit="L1", session_id=session_id,
            )

    # Fast path: L2 semantic cache
    emb = get_embedding_provider()
    query_emb = (await emb.embed([message]))[0]

    l2 = get_l2_cache()
    if l2:
        cached = l2.get(tenant.id, query_emb, threshold=settings.l2_cache_threshold)
        if cached:
            if l1:
                l1.set(tenant.id, message, cached)
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.info("chat_cache_hit", cache_hit="L2", latency_ms=round(elapsed_ms, 2))
            return ChatResponse(
                answer=cached, intent="faq", confidence=1.0,
                sources=[], cache_hit="L2", session_id=session_id,
            )

    # Agent path
    return await _run_agent(tenant, db, session_id, message, query_emb, t0)


async def _run_agent(
    tenant: Tenant,
    db: Session,
    session_id: str,
    message: str,
    query_emb: list[float],
    t0: float,
) -> ChatResponse:
    """Invoke the agent graph and build a ChatResponse from its final state."""
    tenant_config = tenant.config_json or {}
    system_prompt = build_agent_system_prompt(
        tenant.name,
        tenant_config.get("system_prompt_append", ""),
    )

    graph = _get_graph()
    config = {"configurable": {"thread_id": session_id}}

    # Inject runtime context for tools (tenant_slug, db)
    set_runtime(tenant.slug, db)

    initial_state: AgentState = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        "tenant_id": tenant.id,
        "session_id": session_id,
        "handoff": False,
    }

    final_state = await graph.ainvoke(initial_state, config)

    messages = final_state.get("messages", [])
    answer = ""
    last_ai = None
    for m in reversed(messages):
        if hasattr(m, "type") and m.type == "ai" and m.content:
            last_ai = m
            answer = m.content
            break
        elif isinstance(m, dict) and m.get("role") == "assistant" and m.get("content"):
            answer = m["content"]
            break

    # Extract sources from search_knowledge tool output
    sources = []
    for m in messages:
        if hasattr(m, "type") and m.type == "tool" and getattr(m, "name", "") == "search_knowledge":
            try:
                parsed = json.loads(str(m.content))
                sources = parsed.get("results", [])
            except (json.JSONDecodeError, TypeError):
                pass

    handoff = is_handoff_triggered()

    # Persist conversation
    from app.models.conversation import Conversation, Message as MsgModel

    conv = db.query(Conversation).filter(
        Conversation.tenant_id == tenant.id,
        Conversation.session_id == session_id,
    ).first()
    if conv:
        conv.message_count = (conv.message_count or 0) + 1
        if handoff:
            conv.status = "handed_off"
    else:
        conv = Conversation(
            tenant_id=tenant.id, session_id=session_id,
            status="handed_off" if handoff else "active",
        )
        db.add(conv)
        db.flush()

    db.add(MsgModel(conversation_id=conv.id, role="user", content=message))
    db.add(MsgModel(conversation_id=conv.id, role="assistant", content=answer))
    db.commit()

    # Write to caches
    l1 = get_l1_cache()
    l2 = get_l2_cache()
    if l1 and answer:
        l1.set(tenant.id, message, answer)
    if l2 and answer and query_emb:
        l2.set(tenant.id, query_emb, answer)

    elapsed = (time.monotonic() - t0) * 1000
    logger.info("agent_completed", latency_ms=round(elapsed, 2), handoff=handoff)

    return ChatResponse(
        answer=answer,
        intent="human" if handoff else "faq",
        confidence=1.0,
        sources=sources,
        cache_hit="miss",
        session_id=session_id,
        handoff=handoff,
    )


async def process_chat_stream(
    tenant: Tenant,
    db: Session,
    session_id: str,
    message: str,
):
    """Streaming chat — yields SSE events via LangGraph astream_events."""
    t0 = time.monotonic()

    # Fast path: L1 exact cache
    l1 = get_l1_cache()
    if l1:
        cached = l1.get(tenant.id, message)
        if cached:
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.info("chat_stream_cache_hit", cache_hit="L1", latency_ms=round(elapsed_ms, 2))
            yield f"data: {json.dumps({'type': 'done', 'data': {'answer': cached, 'intent': 'faq', 'confidence': 1.0, 'sources': [], 'cache_hit': 'L1', 'session_id': session_id, 'handoff': False}})}\n\n"
            return

    # Fast path: L2 semantic cache
    emb = get_embedding_provider()
    query_emb = (await emb.embed([message]))[0]

    l2 = get_l2_cache()
    if l2:
        cached = l2.get(tenant.id, query_emb, threshold=settings.l2_cache_threshold)
        if cached:
            if l1:
                l1.set(tenant.id, message, cached)
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.info("chat_stream_cache_hit", cache_hit="L2", latency_ms=round(elapsed_ms, 2))
            yield f"data: {json.dumps({'type': 'done', 'data': {'answer': cached, 'intent': 'faq', 'confidence': 1.0, 'sources': [], 'cache_hit': 'L2', 'session_id': session_id, 'handoff': False}})}\n\n"
            return

    # Agent path with streaming
    tenant_config = tenant.config_json or {}
    system_prompt = build_agent_system_prompt(
        tenant.name,
        tenant_config.get("system_prompt_append", ""),
    )

    # Inject runtime context for tools
    set_runtime(tenant.slug, db)

    graph = _get_graph()
    config = {"configurable": {"thread_id": session_id}}

    initial_state: AgentState = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        "tenant_id": tenant.id,
        "session_id": session_id,
        "handoff": False,
    }

    full_answer = ""
    handoff = False

    async for event in graph.astream_events(initial_state, config, version="v2"):
        kind = event.get("event", "")

        if kind == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and chunk.content:
                full_answer += chunk.content
                yield f"data: {json.dumps({'type': 'delta', 'data': chunk.content})}\n\n"

        elif kind == "on_tool_start":
            tool_name = event.get("name", "")
            yield f"data: {json.dumps({'type': 'tool_start', 'data': {'tool': tool_name}})}\n\n"
            if tool_name == "handoff_to_human":
                handoff = True

        elif kind == "on_tool_end":
            tool_name = event.get("name", "")
            tool_output = event.get("data", {}).get("output", "")
            if tool_name == "search_knowledge":
                try:
                    parsed = json.loads(str(tool_output))
                    sources_data = parsed.get("results", [])
                except (json.JSONDecodeError, TypeError):
                    sources_data = []
                yield f"data: {json.dumps({'type': 'sources', 'data': sources_data})}\n\n"

    # Persist conversation
    from app.models.conversation import Conversation, Message as MsgModel

    conv = db.query(Conversation).filter(
        Conversation.tenant_id == tenant.id,
        Conversation.session_id == session_id,
    ).first()
    if conv:
        conv.message_count = (conv.message_count or 0) + 1
        if handoff:
            conv.status = "handed_off"
    else:
        conv = Conversation(
            tenant_id=tenant.id, session_id=session_id,
            status="handed_off" if handoff else "active",
        )
        db.add(conv)
        db.flush()

    db.add(MsgModel(conversation_id=conv.id, role="user", content=message))
    db.add(MsgModel(conversation_id=conv.id, role="assistant", content=full_answer))
    db.commit()

    # Write to caches
    if l1 and full_answer:
        l1.set(tenant.id, message, full_answer)
    if l2 and full_answer and query_emb:
        l2.set(tenant.id, query_emb, full_answer)

    elapsed = (time.monotonic() - t0) * 1000
    logger.info("agent_stream_completed", latency_ms=round(elapsed, 2), handoff=handoff)

    yield f"data: {json.dumps({'type': 'done', 'data': {'answer': full_answer, 'intent': 'human' if handoff else 'faq', 'confidence': 1.0, 'sources': [], 'cache_hit': 'miss', 'session_id': session_id, 'handoff': handoff}})}\n\n"
