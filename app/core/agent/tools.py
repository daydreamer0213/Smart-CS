# app/core/agent/tools.py
"""Agent tools — search_knowledge and handoff_to_human.

Each function is decorated with @tool so LangGraph's ToolNode can
automatically discover and execute them from LLM tool_call requests.

Runtime context (tenant_slug, db_session) is injected via ContextVar,
set by the caller before invoking the graph.  The LLM only sees and
provides the ``query`` / ``reason`` parameters.
"""

import asyncio
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

MAX_VECTOR_DISTANCE = 0.5

# Runtime context — set before each graph invocation
_runtime: ContextVar[dict] = ContextVar("agent_runtime", default={})
_handoff_flag: ContextVar[bool] = ContextVar("agent_handoff", default=False)


def set_runtime(
    tenant_slug: str,
    db_session: Session,
    role: str | None = None,
    tenant_id: str | None = None,
) -> None:
    """Set per-request runtime context. Call before graph.ainvoke / astream_events."""
    _runtime.set({
        "tenant_slug": tenant_slug,
        "tenant_id": tenant_id,
        "db_session": db_session,
        "role": role,
    })
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
    try:
        ctx = _runtime.get()
        tenant_slug = ctx.get("tenant_slug")
        tenant_id = ctx.get("tenant_id")
        db_session = ctx.get("db_session")
        if not tenant_slug or not tenant_id or db_session is None:
            return json.dumps({"status": "UNAVAILABLE", "results": []})

        vs = get_vector_store()
        bm = get_bm25_manager()
        emb = get_embedding_provider()

        query_vec = (await emb.embed([query]))[0]

        # Run vector and BM25 searches in parallel — they are independent
        loop = asyncio.get_running_loop()
        vector_results, bm25_results = await asyncio.gather(
            loop.run_in_executor(None, vs.search, tenant_slug, query_vec, 5),
            loop.run_in_executor(None, bm.search, tenant_slug, query, 5),
        )

        vector_results = [result for result in vector_results if result[1] <= MAX_VECTOR_DISTANCE]
        fused = rrf_fusion(vector_results, bm25_results, top_k=5)

        if not fused:
            return json.dumps({"status": "NO_RESULTS", "results": []})

        from app.models.document import Document, DocumentChunk
        from app.models.knowledge import KnowledgeItem

        doc_ids = [r["doc_id"] for r in fused]
        knowledge_items = (
            db_session.query(KnowledgeItem)
            .filter(
                KnowledgeItem.tenant_id == tenant_id,
                KnowledgeItem.status == "active",
                KnowledgeItem.id.in_(doc_ids),
            )
            .all()
            if doc_ids
            else []
        )
        document_chunks = (
            db_session.query(DocumentChunk, Document)
            .join(Document, DocumentChunk.document_id == Document.id)
            .filter(
                Document.tenant_id == tenant_id,
                Document.status == "ready",
                DocumentChunk.status == "active",
                DocumentChunk.id.in_(doc_ids),
            )
            .all()
            if doc_ids
            else []
        )
        item_map = {item.id: item for item in knowledge_items}
        chunk_map = {chunk.id: (chunk, document) for chunk, document in document_chunks}

        role = ctx.get("role")
        results = []
        for r in fused:
            item = item_map.get(r["doc_id"])
            if item is not None:
                if item.audience_roles and role not in item.audience_roles:
                    continue
                results.append({
                    "id": item.id,
                    "source_type": "knowledge",
                    "title": item.question,
                    "question": item.question,
                    "answer": item.answer,
                    "score": round(r["score"], 4),
                    "retrievers": r["sources"],
                })
                continue
            chunk_entry = chunk_map.get(r["doc_id"])
            if chunk_entry is None:
                continue
            chunk, document = chunk_entry
            if document.audience_roles and role not in document.audience_roles:
                continue
            results.append({
                "id": chunk.id,
                "source_type": "document",
                "document_id": document.id,
                "title": document.filename,
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "score": round(r["score"], 4),
                "retrievers": r["sources"],
            })

        status = "OK" if results else "NO_RESULTS"
        return json.dumps({"status": status, "results": results}, ensure_ascii=False)
    except Exception:
        return json.dumps({"status": "UNAVAILABLE", "results": []})


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
