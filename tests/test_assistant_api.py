"""Single enterprise-assistant chat contract tests."""

from app.config import settings
from app.core.auth.security import hash_password
from app.core.auth.token import create_access_token
from app.models.user import User
from app.services.hr_support_service import create_handoff_draft


def _employee(db, tenant):
    user = User(
        tenant_id=tenant.id,
        email=f"employee-{tenant.id[:8]}@example.com",
        password_hash=hash_password("Password123"),
        display_name="Employee",
        role="employee",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


async def test_assistant_returns_hr_skills_sources_and_pending_handoff(client, db, test_tenant, monkeypatch):
    user = _employee(db, test_tenant)
    sources = [{"source_type": "document", "source_id": "policy-1", "title": "Leave Policy", "excerpt": "Annual leave rules", "score": 0.9}]
    draft = create_handoff_draft(db, test_tenant.id, user.id, "请转 HR 人工", "员工明确要求人工", sources)

    async def fake_hr_agent(*_args, **_kwargs):
        return "已准备待确认的 HR 支持请求。", draft, sources

    monkeypatch.setattr("app.api.assistant.run_hr_agent", fake_hr_agent)
    response = await client.post(
        f"/api/v1/{test_tenant.slug}/assistant/chat",
        headers={"Authorization": f"Bearer {create_access_token(user)}"},
        json={"message": "请转 HR 人工"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["enabled_skills"] == [
        "hr.knowledge.search", "hr.clarify", "hr.support.draft", "hr.support.status",
    ]
    assert body["sources"] == sources
    assert body["pending_handoff"] == {
        "id": draft.id,
        "question": "请转 HR 人工",
        "reason": "员工明确要求人工",
        "sources": sources,
        "status": "pending",
        "expires_at": draft.expires_at.isoformat().replace("+00:00", "Z"),
    }
    assert "pending_action" not in body


async def test_assistant_keeps_history_within_authenticated_user_session(client, db, test_tenant, monkeypatch):
    user = _employee(db, test_tenant)
    seen_history = []

    async def fake_hr_agent(_db, _tenant_id, _tenant_slug, _user, message, history=None):
        seen_history.append(history or [])
        return f"reply:{message}", None, []

    monkeypatch.setattr("app.api.assistant.run_hr_agent", fake_hr_agent)
    headers = {"Authorization": f"Bearer {create_access_token(user)}"}
    first = await client.post(f"/api/v1/{test_tenant.slug}/assistant/chat", headers=headers, json={"session_id": "session-history", "message": "第一句"})
    second = await client.post(f"/api/v1/{test_tenant.slug}/assistant/chat", headers=headers, json={"session_id": "session-history", "message": "第二句"})

    assert first.status_code == second.status_code == 200
    assert seen_history == [[], [{"role": "user", "content": "第一句"}, {"role": "assistant", "content": "reply:第一句"}]]


async def test_assistant_returns_503_when_api_key_is_not_configured(client, db, test_tenant, monkeypatch):
    user = _employee(db, test_tenant)
    monkeypatch.setattr(settings, "llm_api_key", "")

    response = await client.post(
        f"/api/v1/{test_tenant.slug}/assistant/chat",
        headers={"Authorization": f"Bearer {create_access_token(user)}"},
        json={"message": "年假如何计算？"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Assistant model is not configured"


async def test_assistant_returns_readable_unavailable_error(client, db, test_tenant, monkeypatch):
    user = _employee(db, test_tenant)

    async def failed_hr_agent(*_args, **_kwargs):
        raise RuntimeError("provider timeout")

    monkeypatch.setattr("app.api.assistant.run_hr_agent", failed_hr_agent)
    response = await client.post(
        f"/api/v1/{test_tenant.slug}/assistant/chat",
        headers={"Authorization": f"Bearer {create_access_token(user)}"},
        json={"message": "年假如何计算？"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["message"] == {
        "code": "ASSISTANT_UNAVAILABLE", "message": "助手暂时不可用，请稍后重试",
    }
