"""Minimal, transactional business workflow for the local CRM demo."""

from datetime import UTC, date, datetime, timedelta
import re

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.crm import ActionDraft, AuditLog, Contact, Customer, FollowUpTask, Lead, Opportunity
from app.models.user import User
from app.schemas.business import BusinessCommand, CreateLeadCommand, CreateTaskCommand, UpdateLeadCommand

logger = structlog.get_logger()


class BusinessError(Exception):
    def __init__(self, status_code: int, code: str, message: str, extra: dict | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.extra = extra or {}


def _normal(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _require_member(user: User, tenant_id: str) -> None:
    if user.tenant_id != tenant_id:
        raise BusinessError(403, "TENANT_MISMATCH", "无权访问该租户的数据")


def _require_write_role(user: User) -> None:
    if user.role not in {"owner", "admin", "agent"}:
        raise BusinessError(403, "ACTION_FORBIDDEN", "当前角色不能执行该业务操作")


def require_crm_read_role(user: User) -> None:
    """CRM facts are available only to the sales role and tenant admins."""
    if user.role not in {"owner", "admin", "agent"}:
        raise BusinessError(403, "CRM_FORBIDDEN", "当前角色没有 CRM 查询权限")


def _require_tenant_user(db: Session, tenant_id: str, user_id: str) -> None:
    if db.query(User).filter(User.id == user_id, User.tenant_id == tenant_id, User.is_active.is_(True)).first() is None:
        raise BusinessError(422, "INVALID_ASSIGNEE", "负责人必须是当前租户的启用用户")


def _customer_summary(customer: Customer) -> dict:
    return {"id": customer.id, "name": customer.name, "industry": customer.industry, "level": customer.level, "status": customer.status}


def search_customers(db: Session, tenant_id: str, query: str) -> list[dict]:
    keyword = _normal(query.replace("查询客户", "").replace("查客户", "").strip())
    if not keyword:
        return []
    items = db.query(Customer).filter(Customer.tenant_id == tenant_id).all()
    return [_customer_summary(item) for item in items if keyword in item.normalized_name][:5]


def seed_demo_crm(db: Session, tenant_id: str) -> None:
    """Create one clearly fictional local record for the first-run demo."""
    if db.query(Customer).filter(Customer.tenant_id == tenant_id).count():
        return
    customer = Customer(tenant_id=tenant_id, name="华东智造（演示）", normalized_name="华东智造（演示）", industry="制造业", level="A", status="active")
    db.add(customer)
    db.flush()
    db.add(Contact(tenant_id=tenant_id, customer_id=customer.id, name="李明", title="采购总监", email="li.ming@example.invalid", phone="13800000000"))
    db.add(Opportunity(tenant_id=tenant_id, customer_id=customer.id, name="年度设备升级（演示）", amount_cents=5000000, stage="proposal"))
    db.commit()


def get_customer_overview(db: Session, tenant_id: str, customer_id: str) -> dict:
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.tenant_id == tenant_id).first()
    if customer is None:
        raise BusinessError(404, "CUSTOMER_NOT_FOUND", "未找到该客户")
    contacts = db.query(Contact).filter(Contact.customer_id == customer.id, Contact.tenant_id == tenant_id).all()
    opportunities = db.query(Opportunity).filter(Opportunity.customer_id == customer.id, Opportunity.tenant_id == tenant_id).all()
    tasks = db.query(FollowUpTask).filter(FollowUpTask.customer_id == customer.id, FollowUpTask.tenant_id == tenant_id).all()
    return {
        "customer": _customer_summary(customer),
        "contacts": [{"id": c.id, "name": c.name, "title": c.title, "email": c.email, "phone": c.phone} for c in contacts],
        "opportunities": [{"id": o.id, "name": o.name, "amount_cents": o.amount_cents, "stage": o.stage, "expected_close_date": str(o.expected_close_date or "")} for o in opportunities],
        "open_tasks": [{"id": t.id, "title": t.title, "due_date": str(t.due_date), "status": t.status} for t in tasks if t.status == "open"],
    }


def _check_command(db: Session, tenant_id: str, user: User, command: BusinessCommand) -> None:
    _require_member(user, tenant_id)
    _require_write_role(user)
    if isinstance(command, CreateLeadCommand):
        payload = command.payload
        duplicate = db.query(Lead).filter(
            Lead.tenant_id == tenant_id,
            Lead.normalized_company == _normal(payload.company),
            Lead.contact_email == str(payload.contact_email).lower(),
        ).first()
        if duplicate:
            raise BusinessError(409, "DUPLICATE_LEAD", "发现重复线索，请改为更新已有线索", {"lead_id": duplicate.id})
        if payload.owner_user_id and user.role == "agent" and payload.owner_user_id != user.id:
            raise BusinessError(403, "ACTION_FORBIDDEN", "销售只能创建自己负责的线索")
        if payload.owner_user_id:
            _require_tenant_user(db, tenant_id, payload.owner_user_id)
    elif isinstance(command, UpdateLeadCommand):
        lead = db.query(Lead).filter(Lead.id == command.payload.lead_id, Lead.tenant_id == tenant_id).first()
        if lead is None:
            raise BusinessError(404, "LEAD_NOT_FOUND", "未找到该线索")
        if user.role == "agent" and lead.owner_user_id != user.id:
            raise BusinessError(403, "ACTION_FORBIDDEN", "销售只能更新自己负责的线索")
        if command.payload.owner_user_id:
            if user.role == "agent" and command.payload.owner_user_id != user.id:
                raise BusinessError(403, "ACTION_FORBIDDEN", "销售不能转交线索负责人")
            _require_tenant_user(db, tenant_id, command.payload.owner_user_id)
    else:
        payload = command.payload
        if user.role == "agent" and payload.assignee_user_id and payload.assignee_user_id != user.id:
            raise BusinessError(403, "ACTION_FORBIDDEN", "销售只能创建指派给自己的任务")
        if payload.assignee_user_id:
            _require_tenant_user(db, tenant_id, payload.assignee_user_id)
        model = {"customer": Customer, "lead": Lead, "opportunity": Opportunity}[payload.related_type]
        if db.query(model).filter(model.id == payload.related_id, model.tenant_id == tenant_id).first() is None:
            raise BusinessError(404, "RELATED_RECORD_NOT_FOUND", "任务关联的业务对象不存在")


def _summary(command: BusinessCommand) -> str:
    if isinstance(command, CreateLeadCommand):
        p = command.payload
        return f"创建线索：{p.company} / {p.contact_name} / {p.contact_email}"
    if isinstance(command, UpdateLeadCommand):
        return f"更新线索：{command.payload.lead_id}"
    p = command.payload
    return f"创建跟进任务：{p.title}，截止 {p.due_date}"


def create_draft(db: Session, tenant_id: str, user: User, command: BusinessCommand) -> ActionDraft:
    try:
        _check_command(db, tenant_id, user, command)
    except BusinessError as exc:
        if exc.code != "TENANT_MISMATCH":
            db.add(AuditLog(
                tenant_id=tenant_id,
                actor_user_id=user.id,
                action=command.action,
                entity_type="action_draft",
                status="rejected",
                error_code=exc.code,
            ))
            db.commit()
        logger.warning(
            "business_draft_rejected",
            tenant_id=tenant_id,
            actor_user_id=user.id,
            action=command.action,
            error_code=exc.code,
        )
        raise
    draft = ActionDraft(
        tenant_id=tenant_id,
        actor_user_id=user.id,
        action=command.action,
        params_json=command.payload.model_dump(mode="json"),
        summary=_summary(command),
        status="pending",
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=10),
    )
    db.add(draft)
    db.flush()
    db.add(AuditLog(tenant_id=tenant_id, actor_user_id=user.id, action=command.action, entity_type="action_draft", entity_id=draft.id, status="draft_created"))
    db.commit()
    db.refresh(draft)
    logger.info(
        "business_draft_created",
        tenant_id=tenant_id,
        actor_user_id=user.id,
        action=draft.action,
        draft_id=draft.id,
    )
    return draft


def _execute(db: Session, tenant_id: str, user: User, draft: ActionDraft) -> tuple[str, str, dict, dict | None]:
    p = draft.params_json
    if draft.action == "create_lead":
        lead = Lead(tenant_id=tenant_id, company=p["company"], normalized_company=_normal(p["company"]), contact_name=p["contact_name"], contact_email=p["contact_email"].lower(), source=p["source"], owner_user_id=p.get("owner_user_id") or user.id)
        db.add(lead)
        db.flush()
        return "lead", lead.id, {"id": lead.id, "company": lead.company, "stage": lead.stage}, None
    if draft.action == "update_lead":
        lead = db.query(Lead).filter(Lead.id == p["lead_id"], Lead.tenant_id == tenant_id).first()
        if lead is None:
            raise BusinessError(404, "LEAD_NOT_FOUND", "未找到该线索")
        before = {"stage": lead.stage, "owner_user_id": lead.owner_user_id}
        if p.get("stage") is not None:
            lead.stage = p["stage"]
        if p.get("owner_user_id") is not None:
            lead.owner_user_id = p["owner_user_id"]
        return "lead", lead.id, {"id": lead.id, "stage": lead.stage, "owner_user_id": lead.owner_user_id}, before
    related_column = {"customer": "customer_id", "lead": "lead_id", "opportunity": "opportunity_id"}[p["related_type"]]
    values = {"tenant_id": tenant_id, "title": p["title"], "due_date": date.fromisoformat(p["due_date"]), "assignee_user_id": p.get("assignee_user_id") or user.id, "created_by_user_id": user.id, related_column: p["related_id"]}
    task = FollowUpTask(**values)
    db.add(task)
    db.flush()
    return "follow_up_task", task.id, {"id": task.id, "title": task.title, "due_date": str(task.due_date), "status": task.status}, None


def _record_failure(db: Session, tenant_id: str, user: User, draft: ActionDraft | None, code: str, request_id: str | None) -> None:
    db.rollback()
    db.add(AuditLog(tenant_id=tenant_id, actor_user_id=user.id, action=draft.action if draft else "confirm", entity_type="action_draft", entity_id=draft.id if draft else None, status="failed", error_code=code, request_id=request_id))
    db.commit()
    logger.warning(
        "business_confirmation_failed",
        tenant_id=tenant_id,
        actor_user_id=user.id,
        draft_id=draft.id if draft else None,
        error_code=code,
    )


def confirm_draft(db: Session, tenant_id: str, user: User, draft_id: str, idempotency_key: str, request_id: str | None = None) -> tuple[dict, bool, str]:
    _require_member(user, tenant_id)
    existing = db.query(AuditLog).filter(AuditLog.tenant_id == tenant_id, AuditLog.idempotency_key == idempotency_key).first()
    if existing:
        if existing.actor_user_id != user.id:
            logger.warning("business_confirmation_rejected", tenant_id=tenant_id, actor_user_id=user.id, draft_id=draft_id, error_code="IDEMPOTENCY_KEY_CONFLICT")
            raise BusinessError(409, "IDEMPOTENCY_KEY_CONFLICT", "该幂等键已被其他用户使用")
        logger.info("business_confirmation_replayed", tenant_id=tenant_id, actor_user_id=user.id, draft_id=draft_id, audit_id=existing.id)
        return existing.result_json or {}, True, existing.id
    draft = db.query(ActionDraft).filter(ActionDraft.id == draft_id, ActionDraft.tenant_id == tenant_id).first()
    if draft is None:
        logger.warning("business_confirmation_rejected", tenant_id=tenant_id, actor_user_id=user.id, draft_id=draft_id, error_code="DRAFT_NOT_FOUND")
        raise BusinessError(404, "DRAFT_NOT_FOUND", "未找到待确认操作")
    if draft.actor_user_id != user.id:
        logger.warning("business_confirmation_rejected", tenant_id=tenant_id, actor_user_id=user.id, draft_id=draft_id, error_code="DRAFT_FORBIDDEN")
        raise BusinessError(403, "DRAFT_FORBIDDEN", "只能确认自己发起的操作")
    if draft.status != "pending":
        logger.warning("business_confirmation_rejected", tenant_id=tenant_id, actor_user_id=user.id, draft_id=draft_id, error_code="DRAFT_NOT_PENDING")
        raise BusinessError(409, "DRAFT_NOT_PENDING", "该操作已被处理")
    if draft.expires_at < datetime.now(UTC).replace(tzinfo=None):
        draft.status = "expired"
        db.add(AuditLog(tenant_id=tenant_id, actor_user_id=user.id, action=draft.action, entity_type="action_draft", entity_id=draft.id, status="failed", error_code="DRAFT_EXPIRED", request_id=request_id))
        db.commit()
        logger.warning("business_confirmation_expired", tenant_id=tenant_id, actor_user_id=user.id, draft_id=draft.id)
        raise BusinessError(409, "DRAFT_EXPIRED", "操作草稿已过期，请重新发起")
    try:
        # Re-check policy and data immediately before the write.
        command = {"action": draft.action, "payload": draft.params_json}
        if draft.action == "create_lead":
            parsed = CreateLeadCommand.model_validate(command)
        elif draft.action == "update_lead":
            parsed = UpdateLeadCommand.model_validate(command)
        else:
            parsed = CreateTaskCommand.model_validate(command)
        _check_command(db, tenant_id, user, parsed)
        entity_type, entity_id, result, before = _execute(db, tenant_id, user, draft)
        draft.status = "confirmed"
        audit = AuditLog(tenant_id=tenant_id, actor_user_id=user.id, action=draft.action, entity_type=entity_type, entity_id=entity_id, before_json=before, after_json=result, result_json=result, status="success", request_id=request_id, idempotency_key=idempotency_key)
        db.add(audit)
        db.commit()
        db.refresh(audit)
        logger.info(
            "business_action_confirmed",
            tenant_id=tenant_id,
            actor_user_id=user.id,
            action=draft.action,
            entity_type=entity_type,
            entity_id=entity_id,
            audit_id=audit.id,
        )
        return result, False, audit.id
    except BusinessError as exc:
        _record_failure(db, tenant_id, user, draft, exc.code, request_id)
        raise
    except IntegrityError:
        db.rollback()
        replay = db.query(AuditLog).filter(AuditLog.tenant_id == tenant_id, AuditLog.idempotency_key == idempotency_key).first()
        if replay and replay.actor_user_id == user.id:
            logger.info("business_confirmation_replayed", tenant_id=tenant_id, actor_user_id=user.id, draft_id=draft_id, audit_id=replay.id)
            return replay.result_json or {}, True, replay.id
        logger.warning("business_confirmation_failed", tenant_id=tenant_id, actor_user_id=user.id, draft_id=draft_id, error_code="WRITE_CONFLICT")
        raise BusinessError(409, "WRITE_CONFLICT", "数据已变化，请重新发起操作")


def list_audit_logs(db: Session, tenant_id: str, user: User) -> list[dict]:
    _require_member(user, tenant_id)
    if user.role not in {"owner", "admin"}:
        raise BusinessError(403, "AUDIT_FORBIDDEN", "仅管理员可以查看审计日志")
    rows = db.query(AuditLog).filter(AuditLog.tenant_id == tenant_id).order_by(AuditLog.created_at.desc()).limit(100).all()
    return [{"id": row.id, "action": row.action, "entity_type": row.entity_type, "entity_id": row.entity_id, "status": row.status, "error_code": row.error_code, "created_at": row.created_at.isoformat() if row.created_at else ""} for row in rows]
