"""Governed HR service agent with a deliberately small skill catalog."""

import json
import time
from contextvars import ContextVar

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.core.agent.tools import search_knowledge, set_runtime
from app.models.hr import HandoffDraft
from app.models.user import User
from app.services import hr_support_service

logger = structlog.get_logger()

HR_SKILL_NAMES = [
    "hr.knowledge.search",
    "hr.clarify",
    "hr.support.draft",
    "hr.support.status",
]

_runtime: ContextVar[dict] = ContextVar("hr_agent_runtime", default={})

_UNVERIFIED_REPLY = "我无法在未检索到授权 HR 制度来源的情况下确认该政策。请补充信息或申请 HR 人工支持。"
_PENDING_HANDOFF_REPLY = "已准备待用户确认的 HR 支持请求，确认后才会创建正式工单。"


def allowed_hr_skill_names() -> list[str]:
    return HR_SKILL_NAMES.copy()


def set_hr_runtime(db: Session, tenant_id: str, tenant_slug: str, user: User, message: str) -> None:
    set_runtime(tenant_slug, db, user.role, tenant_id)
    _runtime.set({
        "db": db,
        "tenant_id": tenant_id,
        "user": user,
        "message": message,
        "sources": [],
        "clarifying_question": None,
        "draft": None,
        "search_attempted": False,
        "empty_search": False,
        "status_requested": False,
    })


def _ctx() -> dict:
    ctx = _runtime.get()
    if not ctx:
        raise RuntimeError("HR agent runtime is not initialized")
    return ctx


def _source_excerpt(result: dict) -> str:
    return str(result.get("answer") or result.get("content") or result.get("excerpt") or "")[:500]


def _normalize_sources(payload: dict) -> list[dict]:
    sources = []
    for result in payload.get("results", []):
        source_id = result.get("id") or result.get("source_id")
        if not source_id:
            continue
        sources.append({
            "source_type": str(result.get("source_type") or "knowledge"),
            "source_id": str(source_id),
            "title": str(result.get("title") or ""),
            "excerpt": _source_excerpt(result),
            "score": result.get("score"),
        })
    return sources


def _log_tool(ctx: dict, tool_name: str, result_code: str, result_count: int, started: float) -> None:
    logger.info(
        "hr_agent_tool_completed",
        tenant_id=ctx["tenant_id"],
        actor_user_id=ctx["user"].id,
        role=ctx["user"].role,
        tool_name=tool_name,
        result_code=result_code,
        result_count=result_count,
        latency_ms=round((time.monotonic() - started) * 1000, 2),
    )


@tool
async def search_hr_knowledge(query: str) -> str:
    """检索当前员工有权限查看的 HR 制度来源；制度结论前必须先调用。"""
    ctx = _ctx()
    started = time.monotonic()
    ctx["search_attempted"] = True
    try:
        payload = json.loads(await search_knowledge.ainvoke({"query": query}))
    except (TypeError, ValueError):
        payload = {"results": []}
    sources = _normalize_sources(payload)
    ctx["sources"] = sources
    ctx["empty_search"] = not sources
    _log_tool(ctx, "search_hr_knowledge", "OK" if sources else "NO_RESULTS", len(sources), started)
    return json.dumps({"sources": sources, "result_count": len(sources)}, ensure_ascii=False)


@tool
def ask_clarifying_question(question: str) -> str:
    """针对模糊的 HR 问题提出一个澄清问题，不做制度结论。"""
    ctx = _ctx()
    started = time.monotonic()
    ctx["clarifying_question"] = question
    _log_tool(ctx, "ask_clarifying_question", "QUESTION_RECORDED", 1, started)
    return json.dumps({"clarifying_question": question}, ensure_ascii=False)


@tool
def draft_handoff(reason: str) -> str:
    """准备待员工确认的 HR 人工支持草稿；不会创建正式工单。"""
    ctx = _ctx()
    started = time.monotonic()
    draft = ctx.get("draft")
    if draft is None:
        draft = hr_support_service.create_handoff_draft(
            ctx["db"],
            ctx["tenant_id"],
            ctx["user"].id,
            ctx["message"],
            reason,
            ctx["sources"],
        )
        ctx["draft"] = draft
        result_code = "DRAFT_CREATED"
    else:
        result_code = "DRAFT_REUSED"
    _log_tool(ctx, "draft_handoff", result_code, 1, started)
    return json.dumps({"draft_id": draft.id, "status": draft.status, "requires_confirmation": True}, ensure_ascii=False)


@tool
def get_handoff_status() -> str:
    """查询当前员工本人可见的 HR 支持请求状态。"""
    ctx = _ctx()
    started = time.monotonic()
    ctx["status_requested"] = True
    handoffs = hr_support_service.list_my_handoffs(ctx["db"], ctx["tenant_id"], ctx["user"].id)
    _log_tool(ctx, "get_handoff_status", "OK", len(handoffs), started)
    return json.dumps({"handoffs": [handoff.model_dump(mode="json") for handoff in handoffs]}, ensure_ascii=False)


def _system_prompt() -> str:
    return (
        "你是企业 HR 服务助手。回答任何制度、流程或规则结论前，必须先调用 "
        "search_hr_knowledge 并且只能依据返回的授权来源作答。问题含糊时，调用 "
        "ask_clarifying_question。检索无来源、遇到例外情况或用户明确要求人工帮助时，调用 "
        "draft_handoff。draft_handoff 只会准备待用户确认的草稿，绝不得承诺已创建正式工单。"
    )


async def run_hr_agent(
    db: Session,
    tenant_id: str,
    tenant_slug: str,
    user: User,
    message: str,
    history: list[dict[str, str]] | None = None,
) -> tuple[str, HandoffDraft | None, list[dict]]:
    """Run up to three tool rounds and return reply, pending draft, and sources."""
    set_hr_runtime(db, tenant_id, tenant_slug, user, message)
    tools = [search_hr_knowledge, ask_clarifying_question, draft_handoff, get_handoff_status]
    ctx = _ctx()
    started = time.monotonic()
    tool_calls = 0
    logger.info("hr_agent_started", tenant_id=tenant_id, actor_user_id=user.id, role=user.role)
    llm = ChatOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        temperature=0,
        max_tokens=600,
        timeout=settings.agent_timeout_seconds,
    ).bind_tools(tools)
    messages = [SystemMessage(content=_system_prompt())]
    for turn in (history or [])[-settings.max_conversation_turns * 2:]:
        if turn["role"] == "user":
            messages.append(HumanMessage(content=turn["content"]))
        elif turn["role"] == "assistant":
            messages.append(AIMessage(content=turn["content"]))
    messages.append(HumanMessage(content=message))

    try:
        for _ in range(3):
            reply = await llm.ainvoke(messages)
            messages.append(reply)
            if not reply.tool_calls:
                if ctx["clarifying_question"]:
                    return ctx["clarifying_question"], ctx["draft"], ctx["sources"]
                if ctx["draft"]:
                    return _PENDING_HANDOFF_REPLY, ctx["draft"], ctx["sources"]
                if ctx["status_requested"]:
                    return str(reply.content or _UNVERIFIED_REPLY), None, ctx["sources"]
                if not ctx["search_attempted"] or ctx["empty_search"]:
                    return _UNVERIFIED_REPLY, None, ctx["sources"]
                return str(reply.content or _UNVERIFIED_REPLY), None, ctx["sources"]

            for call in reply.tool_calls:
                tool_calls += 1
                selected = next((item for item in tools if item.name == call["name"]), None)
                if selected is None:
                    content = json.dumps({"error": {"code": "TOOL_NOT_ALLOWED"}}, ensure_ascii=False)
                    _log_tool(ctx, call["name"], "NOT_ALLOWED", 0, time.monotonic())
                else:
                    content = await selected.ainvoke(call.get("args", {}))
                messages.append(ToolMessage(content=str(content), tool_call_id=call["id"]))
                if ctx["clarifying_question"]:
                    return ctx["clarifying_question"], ctx["draft"], ctx["sources"]
                if ctx["draft"]:
                    return _PENDING_HANDOFF_REPLY, ctx["draft"], ctx["sources"]

        return _UNVERIFIED_REPLY, ctx["draft"], ctx["sources"]
    finally:
        logger.info(
            "hr_agent_completed",
            tenant_id=tenant_id,
            actor_user_id=user.id,
            role=user.role,
            tool_calls=tool_calls,
            latency_ms=round((time.monotonic() - started) * 1000, 2),
        )
