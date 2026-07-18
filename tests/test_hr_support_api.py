"""HTTP contract tests for the governed HR support handoff lifecycle."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.core.auth.security import hash_password
from app.core.auth.token import create_access_token
from app.models.crm import AuditLog
from app.models.hr import HandoffDraft, SupportHandoff
from app.models.tenant import Tenant
from app.models.user import User
from app.services import hr_support_service

SECRET_QUESTION = "SECRET_QUESTION_cross_region_leave"
SECRET_REASON = "SECRET_REASON_policy_exception"
SECRET_EXCERPT = "SECRET_EXCERPT_internal_policy_text"
SECRET_RESOLUTION_NOTE = "SECRET_RESOLUTION_NOTE_local_exception_confirmed"
OPERATIONAL_AUDIT_KEYS = {
    "id",
    "status",
    "assigned_user_id",
    "resolved_by_user_id",
    "resolved_at",
}


def _user(db, tenant, role, email=None, active=True):
    user = User(
        tenant_id=tenant.id,
        email=email or f"{role}-{tenant.id[:8]}@example.com",
        password_hash=hash_password("Password123"),
        display_name=role,
        role=role,
        is_active=active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _draft(db, tenant, requester, *, expires_at=None):
    draft = HandoffDraft(
        tenant_id=tenant.id,
        requester_user_id=requester.id,
        question=SECRET_QUESTION,
        reason=SECRET_REASON,
        sources_json=[
            {
                "source_type": "document",
                "source_id": "policy-1",
                "title": "Leave policy",
                "excerpt": SECRET_EXCERPT,
                "score": 0.93,
            }
        ],
        expires_at=expires_at or datetime.now(UTC) + timedelta(minutes=10),
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


async def test_employee_confirms_own_pending_draft_and_audit_is_recorded(client, db, test_tenant):
    employee = _user(db, test_tenant, "employee")
    draft = _draft(db, test_tenant, employee)

    response = await client.post(
        f"/api/v1/{test_tenant.slug}/hr-support/drafts/{draft.id}/confirm",
        headers={**_headers(employee), "Idempotency-Key": "confirm-own-0001"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "open"
    assert response.json()["question"] == SECRET_QUESTION
    assert response.json()["reason"] == SECRET_REASON
    assert response.json()["sources"][0]["excerpt"] == SECRET_EXCERPT
    handoff = db.query(SupportHandoff).filter_by(tenant_id=test_tenant.id).one()
    assert handoff.requester_user_id == employee.id
    db.expire_all()
    assert db.query(HandoffDraft).filter_by(id=draft.id).one().status == "confirmed"
    audit = db.query(AuditLog).filter_by(tenant_id=test_tenant.id, action="confirm_handoff").one()
    assert audit.actor_user_id == employee.id
    assert audit.entity_type == "hr_support_handoff"
    assert audit.entity_id == handoff.id
    assert audit.status == "success"
    assert audit.after_json == {
        "id": handoff.id,
        "status": "open",
        "assigned_user_id": None,
        "resolved_by_user_id": None,
        "resolved_at": None,
    }
    assert audit.result_json == {"id": handoff.id}
    assert audit.idempotency_key == f"hr-handoff:{draft.id}:confirm-own-0001"
    audit_json = json.dumps(
        [audit.before_json, audit.after_json, audit.result_json], ensure_ascii=False
    )
    assert all(
        secret not in audit_json
        for secret in (SECRET_QUESTION, SECRET_REASON, SECRET_EXCERPT)
    )


async def test_confirmation_replay_returns_same_handoff_and_no_duplicate(client, db, test_tenant):
    employee = _user(db, test_tenant, "employee")
    draft = _draft(db, test_tenant, employee)
    headers = {**_headers(employee), "Idempotency-Key": "replay-key-0001"}

    first = await client.post(f"/api/v1/{test_tenant.slug}/hr-support/drafts/{draft.id}/confirm", headers=headers)
    replay = await client.post(f"/api/v1/{test_tenant.slug}/hr-support/drafts/{draft.id}/confirm", headers=headers)

    assert first.status_code == replay.status_code == 200
    assert first.json()["id"] == replay.json()["id"]
    assert db.query(SupportHandoff).filter_by(tenant_id=test_tenant.id).count() == 1


def test_stale_pending_read_cannot_create_handoff(db, test_tenant, monkeypatch):
    employee = _user(db, test_tenant, "employee")
    draft = _draft(db, test_tenant, employee)

    def interleave_confirmation(_expires_at):
        draft.status = "confirmed"
        db.flush()
        return False

    monkeypatch.setattr(hr_support_service, "_expired", interleave_confirmation)

    with pytest.raises(hr_support_service.HRSupportError) as error:
        hr_support_service.confirm_handoff_draft(
            db,
            test_tenant.id,
            employee.id,
            draft.id,
            "different-key-0001",
        )

    assert error.value.code == "DRAFT_NOT_PENDING"
    assert db.query(SupportHandoff).filter_by(tenant_id=test_tenant.id).count() == 0


async def test_other_tenant_cannot_confirm_draft_or_reuse_another_employee_key(client, db, test_tenant):
    employee = _user(db, test_tenant, "employee")
    draft = _draft(db, test_tenant, employee)
    key = "same-key-0001"
    confirmed = await client.post(
        f"/api/v1/{test_tenant.slug}/hr-support/drafts/{draft.id}/confirm",
        headers={**_headers(employee), "Idempotency-Key": key},
    )
    assert confirmed.status_code == 200

    other_tenant = Tenant(slug="other-hr-tenant", name="Other HR", config_json={}, is_active=True)
    db.add(other_tenant)
    db.commit()
    other_employee = _user(db, other_tenant, "employee")
    cross_tenant = await client.post(
        f"/api/v1/{other_tenant.slug}/hr-support/drafts/{draft.id}/confirm",
        headers={**_headers(other_employee), "Idempotency-Key": "cross-key-0001"},
    )
    conflict = await client.post(
        f"/api/v1/{test_tenant.slug}/hr-support/drafts/{draft.id}/confirm",
        headers={**_headers(_user(db, test_tenant, "employee", "other-employee@example.com")), "Idempotency-Key": key},
    )

    assert cross_tenant.status_code == 404
    assert conflict.status_code == 409
    assert conflict.json()["error"]["message"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


async def test_my_handoffs_only_returns_callers_requests(client, db, test_tenant):
    employee = _user(db, test_tenant, "employee")
    colleague = _user(db, test_tenant, "employee", "colleague@example.com")
    first = _draft(db, test_tenant, employee)
    second = _draft(db, test_tenant, colleague)
    for draft, user, key in ((first, employee, "my-list-key-01"), (second, colleague, "my-list-key-02")):
        response = await client.post(
            f"/api/v1/{test_tenant.slug}/hr-support/drafts/{draft.id}/confirm",
            headers={**_headers(user), "Idempotency-Key": key},
        )
        assert response.status_code == 200

    response = await client.get(f"/api/v1/{test_tenant.slug}/hr-support/me", headers=_headers(employee))

    assert response.status_code == 200
    assert [item["question"] for item in response.json()] == [first.question]


async def test_admin_list_is_role_protected_and_tenant_scoped(client, db, test_tenant):
    employee = _user(db, test_tenant, "employee")
    owner = _user(db, test_tenant, "owner")
    draft = _draft(db, test_tenant, employee)
    response = await client.post(
        f"/api/v1/{test_tenant.slug}/hr-support/drafts/{draft.id}/confirm",
        headers={**_headers(employee), "Idempotency-Key": "admin-list-key1"},
    )
    assert response.status_code == 200

    other_tenant = Tenant(slug="admin-other-tenant", name="Other HR", config_json={}, is_active=True)
    db.add(other_tenant)
    db.commit()
    other_employee = _user(db, other_tenant, "employee")
    other_draft = _draft(db, other_tenant, other_employee)
    response = await client.post(
        f"/api/v1/{other_tenant.slug}/hr-support/drafts/{other_draft.id}/confirm",
        headers={**_headers(other_employee), "Idempotency-Key": "other-list-key1"},
    )
    assert response.status_code == 200

    forbidden = await client.get(f"/api/v1/{test_tenant.slug}/hr-support/admin", headers=_headers(employee))
    listed = await client.get(f"/api/v1/{test_tenant.slug}/hr-support/admin", headers=_headers(owner))

    assert forbidden.status_code == 403
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["question"] == draft.question


async def test_admin_can_assign_and_resolve_only_active_tenant_users_with_audit(client, db, test_tenant):
    employee = _user(db, test_tenant, "employee")
    owner = _user(db, test_tenant, "owner")
    assignee = _user(db, test_tenant, "admin", "assignee@example.com")
    inactive = _user(db, test_tenant, "admin", "inactive@example.com", active=False)
    draft = _draft(db, test_tenant, employee)
    created = await client.post(
        f"/api/v1/{test_tenant.slug}/hr-support/drafts/{draft.id}/confirm",
        headers={**_headers(employee), "Idempotency-Key": "lifecycle-key01"},
    )
    handoff_id = created.json()["id"]

    invalid = await client.patch(
        f"/api/v1/{test_tenant.slug}/hr-support/admin/{handoff_id}",
        headers=_headers(owner),
        json={"status": "assigned", "assigned_user_id": inactive.id},
    )
    assigned = await client.patch(
        f"/api/v1/{test_tenant.slug}/hr-support/admin/{handoff_id}",
        headers=_headers(owner),
        json={"status": "assigned", "assigned_user_id": assignee.id},
    )
    missing_note = await client.patch(
        f"/api/v1/{test_tenant.slug}/hr-support/admin/{handoff_id}",
        headers=_headers(owner),
        json={"status": "resolved"},
    )
    resolved = await client.patch(
        f"/api/v1/{test_tenant.slug}/hr-support/admin/{handoff_id}",
        headers=_headers(owner),
        json={"status": "resolved", "resolution_note": SECRET_RESOLUTION_NOTE},
    )

    assert invalid.status_code == 422
    assert assigned.status_code == 200
    assert assigned.json()["status"] == "assigned"
    assert missing_note.status_code == 422
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["resolved_by_user_id"] == owner.id
    assert resolved.json()["resolution_note"] == SECRET_RESOLUTION_NOTE
    handoff = db.query(SupportHandoff).filter_by(id=handoff_id).one()
    assert handoff.question == SECRET_QUESTION
    assert handoff.reason == SECRET_REASON
    assert handoff.sources_json[0]["excerpt"] == SECRET_EXCERPT
    assert handoff.resolution_note == SECRET_RESOLUTION_NOTE
    audits = db.query(AuditLog).filter_by(tenant_id=test_tenant.id).all()
    actions = [row.action for row in audits]
    assert actions.count("assign_handoff") == 1
    assert actions.count("resolve_handoff") == 1
    lifecycle_audits = {
        row.action: row for row in audits if row.action in {"assign_handoff", "resolve_handoff"}
    }
    for audit in lifecycle_audits.values():
        assert set(audit.before_json) == OPERATIONAL_AUDIT_KEYS
        assert set(audit.after_json) == OPERATIONAL_AUDIT_KEYS
        assert audit.result_json == {"id": handoff_id}
    assert lifecycle_audits["assign_handoff"].before_json["status"] == "open"
    assert lifecycle_audits["assign_handoff"].after_json["status"] == "assigned"
    assert lifecycle_audits["resolve_handoff"].before_json["status"] == "assigned"
    assert lifecycle_audits["resolve_handoff"].after_json["status"] == "resolved"
    audit_json = json.dumps(
        [[row.before_json, row.after_json, row.result_json] for row in audits],
        ensure_ascii=False,
    )
    assert all(
        secret not in audit_json
        for secret in (SECRET_QUESTION, SECRET_REASON, SECRET_EXCERPT, SECRET_RESOLUTION_NOTE)
    )


async def test_expired_draft_cannot_create_handoff(client, db, test_tenant):
    employee = _user(db, test_tenant, "employee")
    draft = _draft(db, test_tenant, employee, expires_at=datetime.now(UTC) - timedelta(minutes=1))

    response = await client.post(
        f"/api/v1/{test_tenant.slug}/hr-support/drafts/{draft.id}/confirm",
        headers={**_headers(employee), "Idempotency-Key": "expired-key-0001"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["message"]["code"] == "DRAFT_EXPIRED"
    assert db.query(SupportHandoff).filter_by(tenant_id=test_tenant.id).count() == 0
