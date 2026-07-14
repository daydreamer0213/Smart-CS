"""Single enterprise-assistant chat contract tests."""

from app.core.auth.security import hash_password
from app.core.auth.token import create_access_token
from app.models.user import User


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


async def test_assistant_chat_returns_role_scoped_skill_list(client, db, test_tenant, monkeypatch):
    user = _employee(db, test_tenant)

    async def fake_agent(_db, _tenant_id, _tenant_slug, _user, _message, _history=None):
        return "年假制度请以知识库返回内容为准。", None

    monkeypatch.setattr("app.api.assistant.run_business_agent", fake_agent)
    response = await client.post(
        f"/api/v1/{test_tenant.slug}/assistant/chat",
        headers={"Authorization": f"Bearer {create_access_token(user)}"},
        json={"message": "年假如何计算？"},
    )
    assert response.status_code == 200
    assert response.json()["enabled_skills"] == ["knowledge.search"]
    assert "年假" in response.json()["reply"]
    assert response.json()["session_id"]


async def test_assistant_keeps_history_within_authenticated_user_session(client, db, test_tenant, monkeypatch):
    user = _employee(db, test_tenant)
    seen_history = []

    async def fake_agent(_db, _tenant_id, _tenant_slug, _user, message, history=None):
        seen_history.append(history or [])
        return f"reply:{message}", None

    monkeypatch.setattr("app.api.assistant.run_business_agent", fake_agent)
    headers = {"Authorization": f"Bearer {create_access_token(user)}"}
    first = await client.post(f"/api/v1/{test_tenant.slug}/assistant/chat", headers=headers, json={"session_id": "session-history", "message": "第一句"})
    second = await client.post(f"/api/v1/{test_tenant.slug}/assistant/chat", headers=headers, json={"session_id": "session-history", "message": "第二句"})

    assert first.status_code == second.status_code == 200
    assert seen_history == [[], [{"role": "user", "content": "第一句"}, {"role": "assistant", "content": "reply:第一句"}]]


async def test_assistant_returns_readable_unavailable_error(client, db, test_tenant, monkeypatch):
    user = _employee(db, test_tenant)

    async def failed_agent(*_args):
        raise RuntimeError("provider timeout")

    monkeypatch.setattr("app.api.assistant.run_business_agent", failed_agent)
    response = await client.post(
        f"/api/v1/{test_tenant.slug}/assistant/chat",
        headers={"Authorization": f"Bearer {create_access_token(user)}"},
        json={"message": "年假如何计算？"},
    )
    assert response.status_code == 503
    assert response.json()["error"]["message"]["code"] == "ASSISTANT_UNAVAILABLE"
