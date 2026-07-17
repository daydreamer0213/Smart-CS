"""Single authenticated chat surface for the enterprise employee agent."""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_tenant
from app.config import settings
from app.core.agent.hr_agent import allowed_hr_skill_names, run_hr_agent
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.assistant import AssistantChatRequest, AssistantChatResponse
from app.schemas.hr_support import HandoffDraftResponse
from app.services import assistant_service

router = APIRouter(prefix="/api/v1/{tenant_slug}/assistant", tags=["assistant"])
logger = structlog.get_logger()


@router.post("/chat", response_model=AssistantChatResponse)
async def chat(
    body: AssistantChatRequest,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    user: User = Depends(get_current_user),
):
    if user.tenant_id != tenant.id:
        raise HTTPException(
            status_code=403,
            detail={"code": "TENANT_MISMATCH", "message": "无权访问该租户的数据"},
        )
    try:
        logger.info(
            "assistant_chat_requested",
            tenant_id=tenant.id,
            actor_user_id=user.id,
            role=user.role,
            message_length=len(body.message),
        )
        if not settings.llm_api_key:
            logger.warning(
                "assistant_model_unavailable",
                tenant_id=tenant.id,
                actor_user_id=user.id,
                result_code="MISSING_API_KEY",
            )
            raise HTTPException(status_code=503, detail="Assistant model is not configured")
        session_id = body.session_id or str(uuid.uuid4())
        history = assistant_service.load_history(db, tenant.id, user.id, session_id)
        reply, draft, sources = await run_hr_agent(
            db,
            tenant.id,
            tenant.slug,
            user,
            body.message,
            history,
        )
        assistant_service.persist_turn(db, tenant.id, user.id, session_id, body.message, reply)
        pending_handoff = None
        if draft is not None:
            pending_handoff = HandoffDraftResponse(
                id=draft.id,
                question=draft.question,
                reason=draft.reason,
                sources=draft.sources_json or [],
                status=draft.status,
                expires_at=draft.expires_at,
            )
        logger.info(
            "assistant_chat_completed",
            tenant_id=tenant.id,
            actor_user_id=user.id,
            source_count=len(sources),
            has_pending_handoff=bool(draft),
        )
        return AssistantChatResponse(
            session_id=session_id,
            reply=reply,
            enabled_skills=allowed_hr_skill_names(),
            sources=sources,
            pending_handoff=pending_handoff,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "assistant_chat_unavailable",
            tenant_id=tenant.id,
            actor_user_id=user.id,
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail={"code": "ASSISTANT_UNAVAILABLE", "message": "助手暂时不可用，请稍后重试"},
        )
