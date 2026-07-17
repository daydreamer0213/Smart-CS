"""Authenticated HR support handoff endpoints."""

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.admin.auth import require_admin
from app.api.deps import get_current_user, get_db, get_tenant
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.hr_support import HandoffResponse, HandoffStatusUpdate
from app.services import hr_support_service

router = APIRouter(prefix="/api/v1/{tenant_slug}/hr-support", tags=["HR Support"])


def _raise(error: hr_support_service.HRSupportError) -> None:
    raise HTTPException(status_code=error.status_code, detail={"code": error.code, "message": error.message})


def _require_tenant_member(user: User, tenant: Tenant) -> None:
    if user.tenant_id != tenant.id:
        raise HTTPException(status_code=403, detail={"code": "TENANT_MISMATCH", "message": "无权访问该租户的数据"})


@router.post("/drafts/{draft_id}/confirm", response_model=HandoffResponse)
def confirm_draft(
    draft_id: str,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=50),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    user: User = Depends(get_current_user),
):
    _require_tenant_member(user, tenant)
    try:
        return hr_support_service.confirm_handoff_draft(db, tenant.id, user.id, draft_id, idempotency_key)
    except hr_support_service.HRSupportError as exc:
        _raise(exc)


@router.get("/me", response_model=list[HandoffResponse])
def my_handoffs(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    user: User = Depends(get_current_user),
):
    _require_tenant_member(user, tenant)
    return hr_support_service.list_my_handoffs(db, tenant.id, user.id)


@router.get("/admin", response_model=list[HandoffResponse])
def tenant_handoffs(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    user: User = Depends(require_admin),
):
    _require_tenant_member(user, tenant)
    return hr_support_service.list_tenant_handoffs(db, tenant.id)


@router.patch("/admin/{handoff_id}", response_model=HandoffResponse)
def update_handoff(
    handoff_id: str,
    body: HandoffStatusUpdate,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    user: User = Depends(require_admin),
):
    _require_tenant_member(user, tenant)
    try:
        return hr_support_service.update_handoff_status(
            db,
            tenant.id,
            user.id,
            handoff_id,
            body.status,
            body.assigned_user_id,
            body.resolution_note,
        )
    except hr_support_service.HRSupportError as exc:
        _raise(exc)
