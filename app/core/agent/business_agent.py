"""A small tool-calling agent for the local CRM demo.

CRM writes are deliberately absent from the tool list.  The draft tools create
only a pending action; the separate confirmation endpoint performs a write.
"""

import json
import time
from contextvars import ContextVar

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User
from app.schemas.business import CreateLeadCommand, CreateTaskCommand, LeadCreatePayload, TaskCreatePayload, UpdateLeadCommand, LeadUpdatePayload
from app.services import business_service

logger = structlog.get_logger()

_runtime: ContextVar[dict] = ContextVar("business_agent_runtime", default={})


def set_business_runtime(db: Session, tenant_id: str, user: User, tenant_slug: str = "") -> None:
    _runtime.set({"db": db, "tenant_id": tenant_id, "tenant_slug": tenant_slug, "user": user, "draft": None})


def _ctx() -> dict:
    ctx = _runtime.get()
    if not ctx:
        raise RuntimeError("business agent runtime is not initialized")
    return ctx


def _error(exc: business_service.BusinessError) -> str:
    return json.dumps({"error": {"code": exc.code, "message": exc.message, **exc.extra}}, ensure_ascii=False)


def _existing_draft(ctx: dict) -> str | None:
    draft = ctx.get("draft")
    if draft is None:
        return None
    return json.dumps({"draft_id": draft.id, "summary": draft.summary, "requires_confirmation": True, "message": "已有待确认操作，不能再生成第二个草稿"}, ensure_ascii=False)


def allowed_tools(user: User) -> list:
    """Expose skills by role; every CRM tool also validates access itself."""
    tools = [search_enterprise_knowledge]
    if user.role in {"owner", "admin", "agent"}:
        tools.extend([crm_search_customers, crm_get_customer_overview, draft_create_lead, draft_update_lead, draft_create_follow_up_task])
    return tools


def allowed_skill_names(user: User) -> list[str]:
    names = ["knowledge.search"]
    if user.role in {"owner", "admin", "agent"}:
        names.extend(["crm.read", "crm.prepare_change"])
    return names


@tool
def crm_search_customers(query: str) -> str:
    """查询 CRM 中的客户。客户事实必须使用此工具，不得凭空编造。"""
    ctx = _ctx()
    try:
        business_service.require_crm_read_role(ctx["user"])
        return json.dumps({"customers": business_service.search_customers(ctx["db"], ctx["tenant_id"], query)}, ensure_ascii=False)
    except business_service.BusinessError as exc:
        return _error(exc)


@tool
def crm_get_customer_overview(customer_id: str) -> str:
    """查询某个 CRM 客户的联系人、商机和待办全貌。"""
    ctx = _ctx()
    try:
        business_service.require_crm_read_role(ctx["user"])
        return json.dumps(business_service.get_customer_overview(ctx["db"], ctx["tenant_id"], customer_id), ensure_ascii=False)
    except business_service.BusinessError as exc:
        return _error(exc)


@tool
async def search_enterprise_knowledge(query: str) -> str:
    """检索企业制度、流程和字段说明；不得用它回答 CRM 客户或商机事实。"""
    ctx = _ctx()
    if not ctx["tenant_slug"]:
        return json.dumps({"error": {"code": "POLICY_SEARCH_UNAVAILABLE", "message": "缺少租户知识库上下文"}}, ensure_ascii=False)
    from app.core.agent.tools import search_knowledge, set_runtime
    from app.models.knowledge import KnowledgeItem

    set_runtime(ctx["tenant_slug"], ctx["db"], ctx["user"].role)
    raw = await search_knowledge.ainvoke({"query": query})
    try:
        payload = json.loads(raw)
        ids = [item["id"] for item in payload.get("results", []) if item.get("id")]
        items = ctx["db"].query(KnowledgeItem).filter(
            KnowledgeItem.tenant_id == ctx["tenant_id"], KnowledgeItem.id.in_(ids)
        ).all() if ids else []
        visible_ids = {item.id for item in items if not item.audience_roles or ctx["user"].role in item.audience_roles}
        payload["results"] = [item for item in payload.get("results", []) if item.get("id") in visible_ids]
        return json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError, KeyError):
        return json.dumps({"results": [], "message": "知识检索结果暂时不可用"}, ensure_ascii=False)


@tool
def draft_create_lead(company: str, contact_name: str, contact_email: str, source: str) -> str:
    """生成创建线索草稿。此工具不会创建线索，用户确认后才会写入 CRM。"""
    ctx = _ctx()
    if existing := _existing_draft(ctx):
        return existing
    try:
        command = CreateLeadCommand(action="create_lead", payload=LeadCreatePayload(company=company, contact_name=contact_name, contact_email=contact_email, source=source))
        draft = business_service.create_draft(ctx["db"], ctx["tenant_id"], ctx["user"], command)
        ctx["draft"] = draft
        return json.dumps({"draft_id": draft.id, "summary": draft.summary, "requires_confirmation": True}, ensure_ascii=False)
    except business_service.BusinessError as exc:
        return _error(exc)
    except ValueError as exc:
        return json.dumps({"error": {"code": "INVALID_ARGUMENT", "message": str(exc)}}, ensure_ascii=False)


@tool
def draft_update_lead(lead_id: str, stage: str | None = None) -> str:
    """生成更新线索阶段的草稿。不会直接修改线索。"""
    ctx = _ctx()
    if existing := _existing_draft(ctx):
        return existing
    try:
        command = UpdateLeadCommand(action="update_lead", payload=LeadUpdatePayload(lead_id=lead_id, stage=stage))
        draft = business_service.create_draft(ctx["db"], ctx["tenant_id"], ctx["user"], command)
        ctx["draft"] = draft
        return json.dumps({"draft_id": draft.id, "summary": draft.summary, "requires_confirmation": True}, ensure_ascii=False)
    except business_service.BusinessError as exc:
        return _error(exc)
    except ValueError as exc:
        return json.dumps({"error": {"code": "INVALID_ARGUMENT", "message": str(exc)}}, ensure_ascii=False)


@tool
def draft_create_follow_up_task(related_type: str, related_id: str, title: str, due_date: str) -> str:
    """生成跟进任务草稿。不会直接创建任务。截止日期格式为 YYYY-MM-DD。"""
    ctx = _ctx()
    if existing := _existing_draft(ctx):
        return existing
    try:
        command = CreateTaskCommand(action="create_follow_up_task", payload=TaskCreatePayload(related_type=related_type, related_id=related_id, title=title, due_date=due_date))
        draft = business_service.create_draft(ctx["db"], ctx["tenant_id"], ctx["user"], command)
        ctx["draft"] = draft
        return json.dumps({"draft_id": draft.id, "summary": draft.summary, "requires_confirmation": True}, ensure_ascii=False)
    except business_service.BusinessError as exc:
        return _error(exc)
    except ValueError as exc:
        return json.dumps({"error": {"code": "INVALID_ARGUMENT", "message": str(exc)}}, ensure_ascii=False)


async def run_business_agent(db: Session, tenant_id: str, tenant_slug: str, user: User, message: str, history: list[dict[str, str]] | None = None) -> tuple[str, object | None]:
    """Run at most three tool rounds; return any generated pending draft."""
    set_business_runtime(db, tenant_id, user, tenant_slug)
    tools = allowed_tools(user)
    started = time.monotonic()
    tool_calls = 0
    logger.info(
        "assistant_agent_started",
        tenant_id=tenant_id,
        actor_user_id=user.id,
        role=user.role,
        enabled_skills=allowed_skill_names(user),
        message_length=len(message),
    )
    llm = ChatOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url, model=settings.llm_model, temperature=0, max_tokens=600, timeout=settings.agent_timeout_seconds).bind_tools(tools)
    messages = [
        SystemMessage(content=(
            "你是企业员工助手。企业制度、流程和字段说明使用企业知识 Skill；"
            "客户、联系人、线索、商机和任务的事实必须通过 CRM Skill 获得，且仅在该 Skill 可用时才能处理；"
            "没有工具结果时明确说不知道。写操作只能调用 draft 工具生成待确认草稿，绝不能承诺已创建或已更新。"
        )),
    ]
    for turn in (history or [])[-settings.max_conversation_turns * 2:]:
        if turn["role"] == "user":
            messages.append(HumanMessage(content=turn["content"]))
        elif turn["role"] == "assistant":
            messages.append(AIMessage(content=turn["content"]))
    messages.append(HumanMessage(content=message))
    # ponytail: cap tool rounds for the demo; add durable workflow state only if multi-step cases require it.
    try:
        for _ in range(3):
            reply = await llm.ainvoke(messages)
            messages.append(reply)
            if not reply.tool_calls:
                draft = _ctx().get("draft")
                logger.info("assistant_agent_completed", tenant_id=tenant_id, actor_user_id=user.id, tool_calls=tool_calls, has_pending_action=bool(draft), latency_ms=round((time.monotonic() - started) * 1000, 2))
                return str(reply.content or "已完成处理。"), draft
            for call in reply.tool_calls:
                tool_calls += 1
                selected = next((item for item in tools if item.name == call["name"]), None)
                logger.info("assistant_tool_called", tenant_id=tenant_id, actor_user_id=user.id, tool_name=call["name"], allowed=selected is not None)
                if selected is None:
                    content = json.dumps({"error": {"code": "TOOL_NOT_ALLOWED", "message": "工具不在允许列表中"}}, ensure_ascii=False)
                else:
                    content = await selected.ainvoke(call.get("args", {}))
                messages.append(ToolMessage(content=str(content), tool_call_id=call["id"]))
        draft = _ctx().get("draft")
        logger.warning("assistant_agent_round_limit", tenant_id=tenant_id, actor_user_id=user.id, tool_calls=tool_calls, has_pending_action=bool(draft))
        return "操作需要更多信息；未执行任何写入。", draft
    except Exception as exc:
        logger.warning("assistant_agent_failed", tenant_id=tenant_id, actor_user_id=user.id, error_type=type(exc).__name__, tool_calls=tool_calls)
        raise
