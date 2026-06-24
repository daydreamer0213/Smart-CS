# app/core/agent/tools.py
"""Agent tools — search_knowledge and handoff_to_human.

Each function is decorated with @tool so LangGraph's ToolNode can
automatically discover and execute them from LLM tool_call requests.

Runtime context (tenant_slug, db_session) is injected via ContextVar,
set by the caller before invoking the graph.  The LLM only sees and
provides the ``query`` / ``reason`` parameters.
"""

import json
from contextvars import ContextVar

from langchain_core.tools import tool
from sqlalchemy.orm import Session

from app.core.retrieval_module import (
    get_bm25_manager,
    get_embedding_provider,
    get_vector_store,
)
from app.core.retrieval.fusion import rrf_fusion

# Runtime context — set before each graph invocation
_runtime: ContextVar[dict] = ContextVar("agent_runtime", default={})
_handoff_flag: ContextVar[bool] = ContextVar("agent_handoff", default=False)


def set_runtime(tenant_slug: str, db_session: Session) -> None:
    """Set per-request runtime context. Call before graph.ainvoke / astream_events."""
    _runtime.set({"tenant_slug": tenant_slug, "db_session": db_session})
    _handoff_flag.set(False)


def is_handoff_triggered() -> bool:
    """Check if handoff_to_human was called during this graph invocation."""
    return _handoff_flag.get()


@tool
async def search_knowledge(query: str) -> str:
    """搜索知识库获取与用户问题匹配的 FAQ 条目。

    在回答任何用户问题前必须先调用此工具。传入用户的原始问题作为 query，
    返回 JSON 格式的匹配结果列表（可能为空）。
    """
    ctx = _runtime.get()
    tenant_slug = ctx["tenant_slug"]
    db_session = ctx["db_session"]

    vs = get_vector_store()
    bm = get_bm25_manager()
    emb = get_embedding_provider()

    query_vec = (await emb.embed([query]))[0]
    vector_results = vs.search(tenant_slug, query_vec, top_k=5)
    bm25_results = bm.search(tenant_slug, query, top_k=5)

    fused = rrf_fusion(vector_results, bm25_results, top_k=5)

    if not fused:
        return json.dumps({"results": [], "message": "未找到相关知识条目"}, ensure_ascii=False)

    from app.models.knowledge import KnowledgeItem

    doc_ids = [r["doc_id"] for r in fused]
    items = (
        db_session.query(KnowledgeItem)
        .filter(KnowledgeItem.id.in_(doc_ids))
        .all()
        if doc_ids
        else []
    )
    item_map = {item.id: item for item in items}

    results = []
    for r in fused:
        item = item_map.get(r["doc_id"])
        results.append({
            "question": item.question if item else "",
            "answer": item.answer if item else "",
            "score": round(r["score"], 4),
        })

    return json.dumps({"results": results}, ensure_ascii=False)


@tool
async def handoff_to_human(reason: str) -> str:
    """将当前对话转接给人工客服。

    在以下情况调用此工具：
    1. search_knowledge 返回空结果或不相关内容
    2. 用户明确要求转人工、找经理、投诉
    3. 用户情绪激烈或问题明显超出知识库范围
    """
    from app.core.llm.prompts import HANDOFF_MESSAGE

    _handoff_flag.set(True)
    return json.dumps({
        "success": True,
        "message": HANDOFF_MESSAGE,
        "reason": reason,
    }, ensure_ascii=False)
