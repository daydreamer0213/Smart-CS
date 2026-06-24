"""Customer chat endpoint."""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.middleware.tenant import TenantMiddleware
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import process_chat

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
