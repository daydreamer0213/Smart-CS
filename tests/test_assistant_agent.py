"""Observability tests for the role-scoped enterprise agent."""

from langchain_core.messages import AIMessage

from app.core.agent.business_agent import run_business_agent
from app.core.auth.security import hash_password
from app.models.user import User


class CaptureLogger:
    def __init__(self):
        self.events = []

    def info(self, event, **fields):
        self.events.append(("info", event, fields))

    def warning(self, event, **fields):
        self.events.append(("warning", event, fields))


async def test_agent_logs_lifecycle_without_message_content(db, test_tenant, monkeypatch):
    user = User(
        tenant_id=test_tenant.id,
        email=f"employee-agent-{test_tenant.id[:8]}@example.com",
        password_hash=hash_password("Password123"),
        display_name="Employee",
        role="employee",
        is_active=True,
    )
    db.add(user)
    db.commit()

    class FakeLLM:
        def bind_tools(self, _tools):
            return self

        async def ainvoke(self, _messages):
            return AIMessage(content="请参考企业制度文档。")

    capture = CaptureLogger()
    monkeypatch.setattr("app.core.agent.business_agent.ChatOpenAI", lambda **_kwargs: FakeLLM())
    monkeypatch.setattr("app.core.agent.business_agent.logger", capture)

    reply, draft = await run_business_agent(db, test_tenant.id, test_tenant.slug, user, "年假如何计算？")

    assert reply == "请参考企业制度文档。"
    assert draft is None
    names = [event for _, event, _ in capture.events]
    assert names == ["assistant_agent_started", "assistant_agent_completed"]
    start_fields = capture.events[0][2]
    assert start_fields["message_length"] == len("年假如何计算？")
    assert "message" not in start_fields
