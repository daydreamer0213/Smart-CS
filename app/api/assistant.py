"""Single authenticated chat surface for the enterprise employee agent."""

import uuid

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_tenant
from app.config import settings
from app.core.agent.business_agent import allowed_skill_names, run_business_agent
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.assistant import AssistantChatRequest, AssistantChatResponse
from app.schemas.business import ConfirmResponse, DraftResponse
from app.services import assistant_service, business_service

router = APIRouter(prefix="/api/v1/{tenant_slug}/assistant", tags=["assistant"])
logger = structlog.get_logger()


def _raise(error: business_service.BusinessError) -> None:
    raise HTTPException(status_code=error.status_code, detail={"code": error.code, "message": error.message, **error.extra})


@router.post("/chat", response_model=AssistantChatResponse)
async def chat(
    body: AssistantChatRequest,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    user: User = Depends(get_current_user),
):
    try:
        business_service._require_member(user, tenant.id)
        logger.info("assistant_chat_requested", tenant_id=tenant.id, actor_user_id=user.id, role=user.role, message_length=len(body.message))
        if not settings.llm_api_key:
            logger.warning("assistant_model_unavailable", tenant_id=tenant.id, actor_user_id=user.id, reason="missing_api_key")
            raise HTTPException(status_code=503, detail="Assistant model is not configured")
        session_id = body.session_id or str(uuid.uuid4())
        history = assistant_service.load_history(db, tenant.id, user.id, session_id)
        reply, draft = await run_business_agent(db, tenant.id, tenant.slug, user, body.message, history)
        assistant_service.persist_turn(db, tenant.id, user.id, session_id, body.message, reply)
        pending = None if draft is None else DraftResponse(id=draft.id, action=draft.action, summary=draft.summary, status=draft.status, expires_at=draft.expires_at)
        logger.info("assistant_chat_completed", tenant_id=tenant.id, actor_user_id=user.id, has_pending_action=bool(draft))
        return AssistantChatResponse(session_id=session_id, reply=reply, enabled_skills=allowed_skill_names(user), pending_action=pending)
    except business_service.BusinessError as exc:
        _raise(exc)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("assistant_chat_unavailable", tenant_id=tenant.id, actor_user_id=user.id, error_type=type(exc).__name__)
        raise HTTPException(status_code=503, detail={"code": "ASSISTANT_UNAVAILABLE", "message": "助手暂时不可用，请稍后重试"})


@router.post("/action-drafts/{draft_id}/confirm", response_model=ConfirmResponse)
def confirm(
    draft_id: str,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=100),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    user: User = Depends(get_current_user),
):
    try:
        result, replayed, audit_id = business_service.confirm_draft(db, tenant.id, user, draft_id, idempotency_key, request.headers.get("X-Request-ID") or str(uuid.uuid4()))
        return ConfirmResponse(status="success", replayed=replayed, action="confirmed", result=result, audit_id=audit_id)
    except business_service.BusinessError as exc:
        _raise(exc)
