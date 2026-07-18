"""Governed HR service agent with a deliberately small skill catalog."""

import json
import re
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
_UNAVAILABLE_REPLY = "HR 知识检索服务暂时不可用，请稍后重试。"
_PENDING_HANDOFF_REPLY = "已准备待用户确认的 HR 支持请求，确认后才会创建正式工单。"
_CLARIFYING_QUESTIONS = {
    "leave_type": "请说明您想咨询的是年假、病假还是其他假期？",
    "time_range": "请说明您咨询的具体时间范围。",
    "employment_location": "请说明该问题适用的工作国家或地区。",
    "request_type": "请说明您想咨询的具体 HR 事项。",
}
_DEFAULT_CLARIFYING_QUESTION = "请补充您想咨询的具体 HR 事项和相关背景。"


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
        "search_status": None,
        "empty_search": False,
        "status_reply": None,
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


def _has_authorized_citations(reply: str, sources: list[dict]) -> bool:
    cited_ids = re.findall(r"\[source:([^\]\s]+)\]", reply)
    authorized_ids = {source["source_id"] for source in sources}
    return bool(cited_ids) and all(source_id in authorized_ids for source_id in cited_ids)


def _render_authorized_citations(reply: str, sources: list[dict]) -> str:
    if not reply.strip() or not sources:
        return _UNVERIFIED_REPLY
    if _has_authorized_citations(reply, sources):
        return reply
    if re.search(r"\[source:[^\]\s]+\]", reply):
        return _UNVERIFIED_REPLY
    citations = " ".join(f"[source:{source['source_id']}]" for source in sources)
    return f"{reply.rstrip()}\n\n{citations}"


def _format_handoff_status(handoffs: list) -> str:
    if not handoffs:
        return "您当前没有 HR 支持请求。"
    lines = [f"- {handoff.id}: {handoff.status}" for handoff in handoffs]
    return "您的 HR 支持请求状态：\n" + "\n".join(lines)


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
        if not isinstance(payload, dict):
            raise ValueError("retrieval payload must be an object")
        results = payload.get("results", [])
        if not isinstance(results, list) or not all(
            isinstance(result, dict) for result in results
        ):
            raise ValueError("retrieval results must be a list of objects")
    except (TypeError, ValueError):
        payload = {"status": "UNAVAILABLE", "results": []}
    sources = _normalize_sources(payload)
    status = payload.get("status")
    if status is None:
        status = "OK" if sources else "NO_RESULTS"
    elif status not in {"OK", "NO_RESULTS", "UNAVAILABLE"}:
        status = "UNAVAILABLE"
    if status != "OK":
        sources = []
    ctx["sources"] = sources
    ctx["search_status"] = status
    ctx["empty_search"] = not sources
    _log_tool(ctx, "search_hr_knowledge", status, len(sources), started)
    return json.dumps(
        {"status": status, "sources": sources, "result_count": len(sources)},
        ensure_ascii=False,
    )


@tool
def ask_clarifying_question(kind: str) -> str:
    """针对模糊 HR 问题按 kind 提出固定澄清问题，不做制度结论。kind 可选值为 leave_type、time_range、employment_location 或 request_type。"""
    ctx = _ctx()
    started = time.monotonic()
    clarifying_question = _CLARIFYING_QUESTIONS.get(kind, _DEFAULT_CLARIFYING_QUESTION)
    ctx["clarifying_question"] = clarifying_question
    _log_tool(ctx, "ask_clarifying_question", "QUESTION_RECORDED", 1, started)
    return json.dumps({"clarifying_question": clarifying_question}, ensure_ascii=False)


@tool
def draft_handoff(reason: str) -> str:
    """准备待员工确认的 HR 人工支持草稿；不会创建正式工单。"""
    ctx = _ctx()
    started = time.monotonic()
    if ctx["search_status"] == "UNAVAILABLE":
        _log_tool(ctx, "draft_handoff", "UNAVAILABLE", 0, started)
        return json.dumps({"status": "UNAVAILABLE", "requires_confirmation": False})
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
    handoffs = hr_support_service.list_my_handoffs(ctx["db"], ctx["tenant_id"], ctx["user"].id)
    ctx["status_reply"] = _format_handoff_status(handoffs)
    _log_tool(ctx, "get_handoff_status", "OK", len(handoffs), started)
    return json.dumps({"handoffs": [handoff.model_dump(mode="json") for handoff in handoffs]}, ensure_ascii=False)


def _system_prompt() -> str:
    return (
        "你是企业 HR 服务助手。回答任何制度、流程或规则结论前，必须先调用 "
        "search_hr_knowledge 并且只能依据返回的授权来源作答。每个制度回答必须包含至少一个 "
        "[source:<source_id>] 引用，且 source_id 必须来自本次检索结果。问题含糊时，调用 "
        "ask_clarifying_question，并将 kind 设置为 leave_type、time_range、employment_location 或 request_type 之一；"
        "其他值会触发通用澄清问题。检索无来源、遇到例外情况或用户明确要求人工帮助时，调用 "
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
                if not ctx["search_attempted"] or ctx["empty_search"]:
                    return _UNVERIFIED_REPLY, None, ctx["sources"]
                content = str(reply.content or "")
                return _render_authorized_citations(content, ctx["sources"]), None, ctx["sources"]

            for call in reply.tool_calls:
                tool_calls += 1
                selected = next((item for item in tools if item.name == call["name"]), None)
                if selected is None:
                    content = json.dumps({"error": {"code": "TOOL_NOT_ALLOWED"}}, ensure_ascii=False)
                    _log_tool(ctx, "unknown_tool", "NOT_ALLOWED", 0, time.monotonic())
                else:
                    content = await selected.ainvoke(call.get("args", {}))
                messages.append(ToolMessage(content=str(content), tool_call_id=call["id"]))
                if ctx["search_status"] == "UNAVAILABLE":
                    return _UNAVAILABLE_REPLY, None, []
                if ctx["clarifying_question"]:
                    return ctx["clarifying_question"], ctx["draft"], ctx["sources"]
                if ctx["draft"]:
                    return _PENDING_HANDOFF_REPLY, ctx["draft"], ctx["sources"]
                if ctx["status_reply"] is not None:
                    return ctx["status_reply"], None, ctx["sources"]

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
