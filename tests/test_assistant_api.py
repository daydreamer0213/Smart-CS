"""Single enterprise-assistant chat contract tests."""

from pathlib import Path

from app.config import settings
from app.core.auth.security import hash_password
from app.core.auth.token import create_access_token
from app.models.conversation import Conversation, Message
from app.models.tenant import Tenant
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


async def test_assistant_keeps_machine_citation_but_returns_readable_display_reply(
    client, db, test_tenant, monkeypatch
):
    user = _employee(db, test_tenant)
    source_id = "d9f7b879-6f80-46fc-a777-429f5ae59c3b"
    sources = [{
        "source_type": "document",
        "source_id": source_id,
        "title": "北辰科技年假制度",
        "excerpt": "员工工作满一年后享有 5 个工作日年假。",
        "score": 0.9,
    }]

    async def fake_hr_agent(*_args, **_kwargs):
        return f"员工工作满一年后享有 5 个工作日年假。[source:{source_id}]", None, sources

    monkeypatch.setattr("app.api.assistant.run_hr_agent", fake_hr_agent)
    response = await client.post(
        f"/api/v1/{test_tenant.slug}/assistant/chat",
        headers={"Authorization": f"Bearer {create_access_token(user)}"},
        json={"message": "年假如何计算？"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reply"].endswith(f"[source:{source_id}]")
    assert body["sources"][0]["source_id"] == source_id
    assert body["display_reply"] == (
        "员工工作满一年后享有 5 个工作日年假。来源：《北辰科技年假制度》"
    )
    assert source_id not in body["display_reply"]


def test_employee_assistant_page_renders_the_readable_reply_field():
    page = (Path(__file__).parents[1] / "static" / "assistant.html").read_text(
        encoding="utf-8"
    )

    assert "addMessage('assistant',data.display_reply)" in page


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
    events = []

    class CaptureLogger:
        def info(self, event, **fields):
            events.append((event, fields))

        def warning(self, event, **fields):
            events.append((event, fields))

    monkeypatch.setattr("app.api.assistant.logger", CaptureLogger())
    monkeypatch.setattr(settings, "llm_api_key", "")

    response = await client.post(
        f"/api/v1/{test_tenant.slug}/assistant/chat",
        headers={"Authorization": f"Bearer {create_access_token(user)}"},
        json={"message": "年假如何计算？"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Assistant model is not configured"
    unavailable_fields = next(fields for event, fields in events if event == "assistant_model_unavailable")
    assert unavailable_fields["result_code"] == "MISSING_API_KEY"
    assert "reason" not in unavailable_fields


async def test_assistant_cross_tenant_request_has_no_agent_or_history_side_effects(client, db, test_tenant, monkeypatch):
    user = _employee(db, test_tenant)
    other_tenant = Tenant(
        slug=f"other-{test_tenant.slug}",
        name="Other Tenant",
        config_json={},
        is_active=True,
    )
    db.add(other_tenant)
    db.commit()
    session_id = f"cross-tenant-{test_tenant.id}"
    agent_called = False

    async def fail_if_called(*_args, **_kwargs):
        nonlocal agent_called
        agent_called = True
        raise AssertionError("HR agent must not run for a cross-tenant request")

    monkeypatch.setattr("app.api.assistant.run_hr_agent", fail_if_called)
    response = await client.post(
        f"/api/v1/{other_tenant.slug}/assistant/chat",
        headers={"Authorization": f"Bearer {create_access_token(user)}"},
        json={"session_id": session_id, "message": "年假如何计算？"},
    )

    conversations = db.query(Conversation).filter(
        Conversation.visitor_id == user.id,
        Conversation.session_id == session_id,
    )
    assert response.status_code == 403
    assert agent_called is False
    assert conversations.count() == 0
    assert db.query(Message).join(Conversation).filter(
        Conversation.visitor_id == user.id,
        Conversation.session_id == session_id,
    ).count() == 0


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
