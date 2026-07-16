"""Critical safety tests for the local CRM business workflow."""

from datetime import date
import json

from app.core.agent.business_agent import allowed_skill_names, crm_search_customers, search_enterprise_knowledge, set_business_runtime
from app.core.agent.tools import search_knowledge, set_runtime as set_knowledge_runtime
from app.core.auth.security import hash_password
from app.core.auth.token import create_access_token
from app.models.crm import AuditLog, Contact, Customer, FollowUpTask, Lead, Opportunity
from app.models.knowledge import KnowledgeItem
from app.models.user import User


def _user(db, tenant, role="owner"):
    user = User(
        tenant_id=tenant.id,
        email=f"{role}-{tenant.id[:8]}@example.com",
        password_hash=hash_password("Password123"),
        display_name=role,
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _customer(db, tenant, user):
    customer = Customer(tenant_id=tenant.id, name="华东智造", normalized_name="华东智造", industry="制造", level="A", owner_user_id=user.id)
    db.add(customer)
    db.flush()
    db.add(Contact(tenant_id=tenant.id, customer_id=customer.id, name="李明", title="采购总监", email="li@example.com"))
    db.add(Opportunity(tenant_id=tenant.id, customer_id=customer.id, name="年度续约", amount_cents=5000000, expected_close_date=date(2026, 8, 1), owner_user_id=user.id))
    db.commit()
    db.refresh(customer)
    return customer


async def test_customer_overview_comes_from_crm(client, db, test_tenant):
    user = _user(db, test_tenant)
    customer = _customer(db, test_tenant, user)
    response = await client.post(
        f"/api/v1/{test_tenant.slug}/business/chat",
        headers={"Authorization": f"Bearer {create_access_token(user)}"},
        json={"message": "查询客户华东智造", "customer_id": customer.id},
    )
    assert response.status_code == 200
    overview = response.json()["customer_overview"]
    assert overview["customer"]["name"] == "华东智造"
    assert overview["contacts"][0]["email"] == "li@example.com"


def test_business_agent_customer_tool_uses_local_crm(db, test_tenant):
    user = _user(db, test_tenant)
    _customer(db, test_tenant, user)
    set_business_runtime(db, test_tenant.id, user)
    result = json.loads(crm_search_customers.invoke({"query": "华东"}))
    assert result["customers"][0]["name"] == "华东智造"


def test_employee_only_receives_knowledge_skill(db, test_tenant):
    employee = _user(db, test_tenant, "employee")
    assert allowed_skill_names(employee) == ["knowledge.search"]


async def test_knowledge_skill_filters_role_restricted_items(db, test_tenant, monkeypatch):
    employee = _user(db, test_tenant, "employee")
    public = KnowledgeItem(tenant_id=test_tenant.id, question="全员制度", answer="公开", audience_roles=[])
    admin_only = KnowledgeItem(tenant_id=test_tenant.id, question="管理员制度", answer="保密", audience_roles=["admin"])
    db.add_all([public, admin_only])
    db.commit()

    class FakeKnowledgeSearch:
        async def ainvoke(self, _args):
            return json.dumps({"results": [
                {"id": public.id, "question": public.question, "answer": public.answer},
                {"id": admin_only.id, "question": admin_only.question, "answer": admin_only.answer},
            ]})

    monkeypatch.setattr("app.core.agent.tools.search_knowledge", FakeKnowledgeSearch())
    set_business_runtime(db, test_tenant.id, employee, test_tenant.slug)
    result = json.loads(await search_enterprise_knowledge.ainvoke({"query": "制度"}))
    assert [item["id"] for item in result["results"]] == [public.id]


async def test_legacy_knowledge_search_only_returns_public_items(db, test_tenant, monkeypatch):
    public = KnowledgeItem(tenant_id=test_tenant.id, question="全员制度", answer="公开", audience_roles=[])
    admin_only = KnowledgeItem(tenant_id=test_tenant.id, question="管理员制度", answer="保密", audience_roles=["admin"])
    db.add_all([public, admin_only])
    db.commit()

    class FakeEmbedding:
        async def embed(self, _texts):
            return [[0.0]]

    class FakeStore:
        def search(self, *_args):
            return [(public.id, 0.1), (admin_only.id, 0.2)]

    class FakeBm25:
        def search(self, *_args):
            return []

    monkeypatch.setattr("app.core.agent.tools.get_embedding_provider", lambda: FakeEmbedding())
    monkeypatch.setattr("app.core.agent.tools.get_vector_store", lambda: FakeStore())
    monkeypatch.setattr("app.core.agent.tools.get_bm25_manager", lambda: FakeBm25())
    set_knowledge_runtime(test_tenant.slug, db, tenant_id=test_tenant.id)
    result = json.loads(await search_knowledge.ainvoke({"query": "制度"}))
    assert [item["id"] for item in result["results"]] == [public.id]


async def test_employee_cannot_query_crm_through_legacy_business_route(client, db, test_tenant):
    employee = _user(db, test_tenant, "employee")
    response = await client.post(
        f"/api/v1/{test_tenant.slug}/business/chat",
        headers={"Authorization": f"Bearer {create_access_token(employee)}"},
        json={"message": "查询客户 华东"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["message"]["code"] == "CRM_FORBIDDEN"


async def test_confirmed_lead_is_idempotent_audited_and_logged(client, db, test_tenant, monkeypatch):
    events = []

    class CaptureLogger:
        def info(self, event, **fields):
            events.append(("info", event, fields))

        def warning(self, event, **fields):
            events.append(("warning", event, fields))

    monkeypatch.setattr("app.services.business_service.logger", CaptureLogger())
    user = _user(db, test_tenant)
    headers = {"Authorization": f"Bearer {create_access_token(user)}"}
    command = {
        "action": "create_lead",
        "payload": {"company": "上海智联", "contact_name": "张三", "contact_email": "zhang@example.com", "source": "website"},
    }
    draft_response = await client.post(f"/api/v1/{test_tenant.slug}/business/chat", headers=headers, json={"message": "创建线索", "command": command})
    assert draft_response.status_code == 200
    draft_id = draft_response.json()["pending_action"]["id"]
    assert db.query(Lead).filter(Lead.tenant_id == test_tenant.id).count() == 0

    confirm_headers = {**headers, "Idempotency-Key": "lead-create-0001"}
    first = await client.post(f"/api/v1/{test_tenant.slug}/business/action-drafts/{draft_id}/confirm", headers=confirm_headers)
    replay = await client.post(f"/api/v1/{test_tenant.slug}/business/action-drafts/{draft_id}/confirm", headers=confirm_headers)

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert db.query(Lead).filter(Lead.tenant_id == test_tenant.id).count() == 1
    assert db.query(AuditLog).filter(AuditLog.tenant_id == test_tenant.id, AuditLog.status == "success").count() == 1
    names = [event for _, event, _ in events]
    assert "business_draft_created" in names
    assert "business_action_confirmed" in names
    assert "business_confirmation_replayed" in names
    for _, _, fields in events:
        assert "contact_email" not in fields


async def test_confirmed_follow_up_task_is_created_for_related_customer(client, db, test_tenant):
    user = _user(db, test_tenant)
    customer = _customer(db, test_tenant, user)
    headers = {"Authorization": f"Bearer {create_access_token(user)}"}
    draft = await client.post(
        f"/api/v1/{test_tenant.slug}/business/chat", headers=headers,
        json={"message": "下周跟进报价", "command": {"action": "create_follow_up_task", "payload": {"related_type": "customer", "related_id": customer.id, "title": "跟进报价", "due_date": "2026-07-20"}}},
    )
    assert draft.status_code == 200
    draft_id = draft.json()["pending_action"]["id"]
    confirmed = await client.post(f"/api/v1/{test_tenant.slug}/business/action-drafts/{draft_id}/confirm", headers={**headers, "Idempotency-Key": "task-create-0001"})
    assert confirmed.status_code == 200
    assert db.query(FollowUpTask).filter(FollowUpTask.tenant_id == test_tenant.id).count() == 1


async def test_duplicate_lead_and_foreign_lead_update_are_rejected(client, db, test_tenant):
    owner = _user(db, test_tenant, "owner")
    agent = _user(db, test_tenant, "agent")
    lead = Lead(tenant_id=test_tenant.id, company="已有客户", normalized_company="已有客户", contact_name="王五", contact_email="wang@example.com", source="manual", owner_user_id=owner.id)
    db.add(lead)
    db.commit()

    owner_headers = {"Authorization": f"Bearer {create_access_token(owner)}"}
    duplicate = await client.post(
        f"/api/v1/{test_tenant.slug}/business/chat", headers=owner_headers,
        json={"message": "创建线索", "command": {"action": "create_lead", "payload": {"company": "已有 客户", "contact_name": "王五", "contact_email": "wang@example.com", "source": "manual"}}},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["message"]["code"] == "DUPLICATE_LEAD"
    rejected = db.query(AuditLog).filter(
        AuditLog.tenant_id == test_tenant.id,
        AuditLog.status == "rejected",
        AuditLog.error_code == "DUPLICATE_LEAD",
    ).one()
    assert rejected.action == "create_lead"

    agent_headers = {"Authorization": f"Bearer {create_access_token(agent)}"}
    forbidden = await client.post(
        f"/api/v1/{test_tenant.slug}/business/chat", headers=agent_headers,
        json={"message": "更新线索", "command": {"action": "update_lead", "payload": {"lead_id": lead.id, "stage": "qualified"}}},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["message"]["code"] == "ACTION_FORBIDDEN"
