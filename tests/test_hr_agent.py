"""Governed HR agent behavior tests."""

import json
from types import SimpleNamespace

from langchain_core.messages import AIMessage

from app.core.agent.hr_agent import allowed_hr_skill_names, run_hr_agent
from app.core.auth.security import hash_password
from app.models.hr import SupportHandoff
from app.models.user import User


def make_employee(db, tenant):
    employee = User(
        tenant_id=tenant.id,
        email=f"hr-agent-{tenant.id[:8]}@example.com",
        password_hash=hash_password("Password123"),
        display_name="HR Employee",
        role="employee",
        is_active=True,
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return employee


class _FakeLLM:
    replies = []

    def __init__(self):
        self.replies = list(self.replies)

    def bind_tools(self, tools):
        self.tools = tools
        return self

    async def ainvoke(self, _messages):
        return self.replies.pop(0)


class FakeDraftLLM(_FakeLLM):
    replies = [
        AIMessage(
            content="",
            tool_calls=[{"name": "draft_handoff", "args": {"reason": "需要 HR 处理跨境例外"}, "id": "draft-1"}],
        )
    ]


class FakeClarifyingLLM(_FakeLLM):
    replies = [
        AIMessage(
            content="",
            tool_calls=[{"name": "ask_clarifying_question", "args": {"question": "请说明您想了解哪类假期？"}, "id": "clarify-1"}],
        )
    ]


class FakeUnsupportedAnswerLLM(_FakeLLM):
    replies = [AIMessage(content="跨境期间年假按当地标准执行。")]


class FakeSearchLLM(_FakeLLM):
    replies = [
        AIMessage(
            content="",
            tool_calls=[{"name": "search_hr_knowledge", "args": {"query": "年假"}, "id": "search-1"}],
        ),
        AIMessage(content="请参考已检索到的年假制度。"),
    ]


class FakeStatusLLM(_FakeLLM):
    replies = [
        AIMessage(
            content="",
            tool_calls=[{"name": "get_handoff_status", "args": {}, "id": "status-1"}],
        ),
        AIMessage(content="您的请求当前为 open。"),
    ]


def test_hr_agent_exposes_only_hr_skills():
    assert allowed_hr_skill_names() == [
        "hr.knowledge.search",
        "hr.clarify",
        "hr.support.draft",
        "hr.support.status",
    ]


async def test_hr_agent_can_prepare_handoff_draft(db, test_tenant, monkeypatch):
    employee = make_employee(db, test_tenant)
    monkeypatch.setattr("app.core.agent.hr_agent.ChatOpenAI", lambda **_kwargs: FakeDraftLLM())

    reply, draft, sources = await run_hr_agent(
        db, test_tenant.id, test_tenant.slug, employee, "跨境工作期间年假怎么处理？"
    )

    assert reply == "已准备待用户确认的 HR 支持请求，确认后才会创建正式工单。"
    assert draft.question == "跨境工作期间年假怎么处理？"
    assert draft.status == "pending"
    assert sources == []


async def test_hr_agent_returns_clarifying_question_directly(db, test_tenant, monkeypatch):
    employee = make_employee(db, test_tenant)
    monkeypatch.setattr("app.core.agent.hr_agent.ChatOpenAI", lambda **_kwargs: FakeClarifyingLLM())

    reply, draft, sources = await run_hr_agent(db, test_tenant.id, test_tenant.slug, employee, "我的假期怎么办？")

    assert reply == "请说明您想了解哪类假期？"
    assert draft is None
    assert sources == []


async def test_hr_agent_blocks_unsupported_policy_answer_without_tool(db, test_tenant, monkeypatch):
    employee = make_employee(db, test_tenant)
    monkeypatch.setattr("app.core.agent.hr_agent.ChatOpenAI", lambda **_kwargs: FakeUnsupportedAnswerLLM())

    reply, draft, sources = await run_hr_agent(db, test_tenant.id, test_tenant.slug, employee, "跨境年假规则是什么？")

    assert reply == "我无法在未检索到授权 HR 制度来源的情况下确认该政策。请补充信息或申请 HR 人工支持。"
    assert draft is None
    assert sources == []


async def test_hr_agent_normalizes_authorized_search_sources(db, test_tenant, monkeypatch):
    employee = make_employee(db, test_tenant)

    async def fake_search(_args):
        return json.dumps({"results": [{"id": "policy-1", "source_type": "knowledge", "title": "年假制度", "answer": "年假规则", "score": 0.91}]})

    monkeypatch.setattr("app.core.agent.hr_agent.ChatOpenAI", lambda **_kwargs: FakeSearchLLM())
    monkeypatch.setattr(
        "app.core.agent.hr_agent.search_knowledge",
        SimpleNamespace(ainvoke=fake_search),
    )

    reply, draft, sources = await run_hr_agent(db, test_tenant.id, test_tenant.slug, employee, "年假怎么算？")

    assert reply == "请参考已检索到的年假制度。"
    assert draft is None
    assert sources == [{"source_type": "knowledge", "source_id": "policy-1", "title": "年假制度", "excerpt": "年假规则", "score": 0.91}]


async def test_hr_agent_status_only_lists_current_employee_handoffs(db, test_tenant, monkeypatch):
    from app.services import hr_support_service

    employee = make_employee(db, test_tenant)
    other = User(
        tenant_id=test_tenant.id,
        email=f"other-{test_tenant.id[:8]}@example.com",
        password_hash=hash_password("Password123"),
        display_name="Other Employee",
        role="employee",
        is_active=True,
    )
    db.add(other)
    db.commit()
    for user in (employee, other):
        draft = hr_support_service.create_handoff_draft(db, test_tenant.id, user.id, "需要帮助", "需要 HR", [])
        hr_support_service.confirm_handoff_draft(db, test_tenant.id, user.id, draft.id, f"status-{user.id[:8]}")

    monkeypatch.setattr("app.core.agent.hr_agent.ChatOpenAI", lambda **_kwargs: FakeStatusLLM())
    reply, draft, sources = await run_hr_agent(db, test_tenant.id, test_tenant.slug, employee, "查询我的工单状态")

    assert reply == "您的请求当前为 open。"
    assert draft is None
    assert sources == []
    assert db.query(SupportHandoff).filter_by(tenant_id=test_tenant.id).count() == 2


async def test_hr_agent_logs_metadata_without_sensitive_payloads(db, test_tenant, monkeypatch):
    from app.core.agent import hr_agent

    class CaptureLogger:
        def __init__(self):
            self.events = []

        def info(self, event, **fields):
            self.events.append((event, fields))

        def warning(self, event, **fields):
            self.events.append((event, fields))

    employee = make_employee(db, test_tenant)
    capture = CaptureLogger()
    monkeypatch.setattr(hr_agent, "logger", capture)
    monkeypatch.setattr("app.core.agent.hr_agent.ChatOpenAI", lambda **_kwargs: FakeDraftLLM())

    await hr_agent.run_hr_agent(db, test_tenant.id, test_tenant.slug, employee, "跨境工作期间年假怎么处理？")

    fields = [str(event) for event in capture.events]
    assert all("跨境工作" not in event and "需要 HR 处理" not in event for event in fields)
    assert any("tool_name" in event and "result_code" in event and "latency_ms" in event for event in fields)
