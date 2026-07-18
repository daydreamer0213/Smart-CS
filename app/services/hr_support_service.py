"""Tenant-scoped, confirmation-gated HR support handoff operations."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.crm import AuditLog
from app.models.hr import HandoffDraft, SupportHandoff
from app.models.user import User
from app.schemas.hr_support import HandoffResponse


class HRSupportError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message


def _handoff_response(handoff: SupportHandoff) -> HandoffResponse:
    return HandoffResponse(
        id=handoff.id,
        question=handoff.question,
        reason=handoff.reason,
        sources=handoff.sources_json or [],
        status=handoff.status,
        assigned_user_id=handoff.assigned_user_id,
        resolved_by_user_id=handoff.resolved_by_user_id,
        resolution_note=handoff.resolution_note,
        resolved_at=handoff.resolved_at,
    )


def _handoff_audit_state(handoff: SupportHandoff) -> dict:
    return {
        "id": handoff.id,
        "status": handoff.status,
        "assigned_user_id": handoff.assigned_user_id,
        "resolved_by_user_id": handoff.resolved_by_user_id,
        "resolved_at": handoff.resolved_at.isoformat() if handoff.resolved_at else None,
    }


def _expired(expires_at: datetime) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= datetime.now(UTC)


def create_handoff_draft(
    db: Session,
    tenant_id: str,
    requester_user_id: str,
    question: str,
    reason: str,
    sources: list[dict],
) -> HandoffDraft:
    draft = HandoffDraft(
        tenant_id=tenant_id,
        requester_user_id=requester_user_id,
        question=question,
        reason=reason,
        sources_json=sources,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def confirm_handoff_draft(
    db: Session,
    tenant_id: str,
    requester_user_id: str,
    draft_id: str,
    idempotency_key: str,
) -> HandoffResponse:
    key = f"hr-handoff:{draft_id}:{idempotency_key}"
    existing = db.query(AuditLog).filter(
        AuditLog.tenant_id == tenant_id,
        AuditLog.idempotency_key == key,
    ).first()
    if existing:
        if existing.actor_user_id != requester_user_id:
            raise HRSupportError(409, "IDEMPOTENCY_KEY_CONFLICT", "该幂等键已被其他用户使用")
        handoff_id = (existing.result_json or {}).get("id")
        handoff = db.query(SupportHandoff).filter(
            SupportHandoff.tenant_id == tenant_id,
            SupportHandoff.id == handoff_id,
        ).first()
        if handoff is None:
            raise HRSupportError(409, "IDEMPOTENCY_REPLAY_INVALID", "幂等请求结果不可用")
        return _handoff_response(handoff)

    draft = db.query(HandoffDraft).filter(
        HandoffDraft.tenant_id == tenant_id,
        HandoffDraft.requester_user_id == requester_user_id,
        HandoffDraft.id == draft_id,
    ).first()
    if draft is None:
        raise HRSupportError(404, "HANDOFF_DRAFT_NOT_FOUND", "未找到可确认的转人工草稿")
    if draft.status != "pending":
        raise HRSupportError(409, "DRAFT_NOT_PENDING", "该转人工草稿已被处理")
    if _expired(draft.expires_at):
        draft.status = "expired"
        db.commit()
        raise HRSupportError(409, "DRAFT_EXPIRED", "转人工草稿已过期，请重新发起")

    claimed = db.query(HandoffDraft).filter(
        HandoffDraft.tenant_id == tenant_id,
        HandoffDraft.requester_user_id == requester_user_id,
        HandoffDraft.id == draft_id,
        HandoffDraft.status == "pending",
    ).update({HandoffDraft.status: "confirmed"}, synchronize_session=False)
    if claimed == 0:
        db.rollback()
        replay = db.query(AuditLog).filter(
            AuditLog.tenant_id == tenant_id,
            AuditLog.idempotency_key == key,
        ).first()
        if replay and replay.actor_user_id == requester_user_id:
            replay_handoff = db.query(SupportHandoff).filter(
                SupportHandoff.tenant_id == tenant_id,
                SupportHandoff.id == (replay.result_json or {}).get("id"),
            ).first()
            if replay_handoff:
                return _handoff_response(replay_handoff)
        raise HRSupportError(409, "DRAFT_NOT_PENDING", "该转人工草稿已被处理")

    handoff = SupportHandoff(
        tenant_id=tenant_id,
        requester_user_id=requester_user_id,
        question=draft.question,
        reason=draft.reason,
        sources_json=draft.sources_json or [],
        status="open",
    )
    db.add(handoff)
    db.flush()
    db.add(AuditLog(
        tenant_id=tenant_id,
        actor_user_id=requester_user_id,
        action="confirm_handoff",
        entity_type="hr_support_handoff",
        entity_id=handoff.id,
        after_json=_handoff_audit_state(handoff),
        result_json={"id": handoff.id},
        status="success",
        idempotency_key=key,
    ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        replay = db.query(AuditLog).filter(
            AuditLog.tenant_id == tenant_id,
            AuditLog.idempotency_key == key,
        ).first()
        if replay and replay.actor_user_id == requester_user_id:
            replay_handoff = db.query(SupportHandoff).filter(
                SupportHandoff.tenant_id == tenant_id,
                SupportHandoff.id == (replay.result_json or {}).get("id"),
            ).first()
            if replay_handoff:
                return _handoff_response(replay_handoff)
        raise HRSupportError(409, "IDEMPOTENCY_KEY_CONFLICT", "该幂等键已被其他用户使用")
    db.refresh(handoff)
    return _handoff_response(handoff)


def list_my_handoffs(db: Session, tenant_id: str, requester_user_id: str) -> list[HandoffResponse]:
    rows = db.query(SupportHandoff).filter(
        SupportHandoff.tenant_id == tenant_id,
        SupportHandoff.requester_user_id == requester_user_id,
    ).order_by(SupportHandoff.created_at.desc()).all()
    return [_handoff_response(row) for row in rows]


def list_tenant_handoffs(db: Session, tenant_id: str) -> list[HandoffResponse]:
    rows = db.query(SupportHandoff).filter(
        SupportHandoff.tenant_id == tenant_id,
    ).order_by(SupportHandoff.created_at.desc()).all()
    return [_handoff_response(row) for row in rows]


def update_handoff_status(
    db: Session,
    tenant_id: str,
    actor_user_id: str,
    handoff_id: str,
    status: str,
    assigned_user_id: str | None,
    resolution_note: str | None,
) -> HandoffResponse:
    handoff = db.query(SupportHandoff).filter(
        SupportHandoff.tenant_id == tenant_id,
        SupportHandoff.id == handoff_id,
    ).first()
    if handoff is None:
        raise HRSupportError(404, "HANDOFF_NOT_FOUND", "未找到 HR 支持请求")

    if status == "assigned":
        assignee = db.query(User).filter(
            User.tenant_id == tenant_id,
            User.id == assigned_user_id,
            User.is_active.is_(True),
        ).first()
        if assignee is None:
            raise HRSupportError(422, "ASSIGNEE_INVALID", "被指派人必须是当前租户的活跃用户")
        if handoff.status != "open":
            raise HRSupportError(409, "HANDOFF_STATUS_INVALID", "仅 open 请求可被指派")
        before = _handoff_audit_state(handoff)
        handoff.assigned_user_id = assignee.id
        handoff.status = "assigned"
        action = "assign_handoff"
    elif status == "resolved":
        if handoff.status not in {"open", "assigned"}:
            raise HRSupportError(409, "HANDOFF_STATUS_INVALID", "仅 open 或 assigned 请求可被解决")
        if not (resolution_note or "").strip():
            raise HRSupportError(422, "RESOLUTION_NOTE_REQUIRED", "解决请求必须填写处理说明")
        before = _handoff_audit_state(handoff)
        handoff.status = "resolved"
        handoff.resolved_by_user_id = actor_user_id
        handoff.resolution_note = resolution_note.strip()
        handoff.resolved_at = datetime.now(UTC)
        action = "resolve_handoff"
    else:
        raise HRSupportError(409, "HANDOFF_STATUS_INVALID", "不支持该状态变更")

    db.flush()
    after = _handoff_audit_state(handoff)
    db.add(AuditLog(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type="hr_support_handoff",
        entity_id=handoff.id,
        before_json=before,
        after_json=after,
        result_json={"id": handoff.id},
        status="success",
    ))
    db.commit()
    db.refresh(handoff)
    return _handoff_response(handoff)
