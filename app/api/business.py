"""Protected local CRM sales-assistant endpoints."""

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_tenant
from app.core.agent.business_agent import run_business_agent
from app.config import settings
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.business import BusinessChatRequest, BusinessChatResponse, ConfirmResponse, DraftResponse
from app.services import business_service

router = APIRouter(prefix="/api/v1/{tenant_slug}/business", tags=["business"])


def _raise(error: business_service.BusinessError) -> None:
    raise HTTPException(status_code=error.status_code, detail={"code": error.code, "message": error.message, **error.extra})


@router.post("/chat", response_model=BusinessChatResponse, deprecated=True)
async def chat(
    body: BusinessChatRequest,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    user: User = Depends(get_current_user),
):
    try:
        business_service._require_member(user, tenant.id)
        if body.command:
            draft = business_service.create_draft(db, tenant.id, user, body.command)
            return BusinessChatResponse(reply="已生成待确认操作，请核对字段后确认。", pending_action=DraftResponse(id=draft.id, action=draft.action, summary=draft.summary, status=draft.status, expires_at=draft.expires_at))
        if body.customer_id:
            business_service.require_crm_read_role(user)
            overview = business_service.get_customer_overview(db, tenant.id, body.customer_id)
            return BusinessChatResponse(reply="以下内容来自本地 CRM 查询，不来自知识库。", customer_overview=overview)
        if settings.llm_api_key and not body.message.strip().startswith(("查询客户", "查客户")):
            reply, draft = await run_business_agent(db, tenant.id, tenant.slug, user, body.message)
            pending = None if draft is None else DraftResponse(id=draft.id, action=draft.action, summary=draft.summary, status=draft.status, expires_at=draft.expires_at)
            return BusinessChatResponse(reply=reply, pending_action=pending)
        business_service.require_crm_read_role(user)
        customers = business_service.search_customers(db, tenant.id, body.message)
        return BusinessChatResponse(reply="找到客户，请选择一条查看全貌。" if customers else "没有找到客户。可改用完整名称查询，或通过操作草稿创建线索。", customers=customers)
    except business_service.BusinessError as exc:
        _raise(exc)


@router.post("/action-drafts/{draft_id}/confirm", response_model=ConfirmResponse, deprecated=True)
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


@router.get("/audit-logs", deprecated=True)
def audit_logs(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    user: User = Depends(get_current_user),
):
    try:
        return {"items": business_service.list_audit_logs(db, tenant.id, user)}
    except business_service.BusinessError as exc:
        _raise(exc)
