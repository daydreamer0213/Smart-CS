"""Customer chat endpoint — non-streaming POST and SSE streaming GET."""

import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.chat import ChatRequest
from app.services.chat_service import process_chat, process_chat_stream

router = APIRouter()


@router.post("/api/v1/{tenant_slug}/chat", deprecated=True)
async def chat(
    request: Request,
    body: ChatRequest,
    db: Session = Depends(get_db),
):
    """Non-streaming chat — returns a complete ChatResponse."""
    tenant = request.state.tenant
    session_id = body.session_id or str(uuid.uuid4())

    return await process_chat(
        tenant=tenant,
        db=db,
        session_id=session_id,
        message=body.message,
    )


@router.get("/api/v1/{tenant_slug}/chat/stream", deprecated=True)
async def chat_stream(
    request: Request,
    session_id: str = Query(""),
    message: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    """SSE streaming chat endpoint.

    Yields ``text/event-stream`` with events:
        tool_start  — agent started calling a tool (e.g. search_knowledge)
        sources     — retrieval results from search_knowledge
        delta       — incremental LLM text token
        tool_end    — tool execution completed
        done        — final ChatResponse dict (or cached answer / handoff)

    Frontend JS handles tool_start/tool_end events to show
    "正在搜索知识库..." transition state.
    """
    tenant = request.state.tenant
    session_id = session_id or str(uuid.uuid4())
    return StreamingResponse(
        process_chat_stream(tenant, db, session_id, message),
        media_type="text/event-stream",
        headers={"X-Request-ID": str(uuid.uuid4())},
    )
