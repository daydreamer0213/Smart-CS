"""Customer chat endpoint."""

import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.middleware.tenant import TenantMiddleware
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import process_chat, process_chat_stream

router = APIRouter()


@router.post("/api/v1/{tenant_slug}/chat")
async def chat(
    request: Request,
    body: ChatRequest,
    db: Session = Depends(get_db),
):
    tenant = request.state.tenant
    session_id = body.session_id or str(uuid.uuid4())

    return await process_chat(
        tenant=tenant,
        db=db,
        session_id=session_id,
        message=body.message,
    )


@router.get("/api/v1/{tenant_slug}/chat/stream")
async def chat_stream(
    request: Request,
    session_id: str = Query(""),
    message: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    """SSE streaming chat endpoint.

    Yields ``text/event-stream`` with events:
        sources -- hybrid retrieval results
        delta   -- incremental LLM content token
        done    -- final ChatResponse dict (or cached answer / handoff)
    """
    tenant = request.state.tenant
    session_id = session_id or str(uuid.uuid4())
    return StreamingResponse(
        process_chat_stream(db, tenant, session_id, message),
        media_type="text/event-stream",
        headers={"X-Request-ID": str(uuid.uuid4())},
    )
