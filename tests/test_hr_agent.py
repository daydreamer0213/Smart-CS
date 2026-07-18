"""Governed HR agent behavior tests."""

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from app.core.agent.hr_agent import allowed_hr_skill_names, run_hr_agent
from app.core.auth.security import hash_password
from app.models.hr import HandoffDraft, SupportHandoff
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
        self.calls = 0

    def bind_tools(self, tools):
        self.tools = tools
        return self

    async def ainvoke(self, _messages):
        self.calls += 1
        return self.replies.pop(0)


async def test_hr_agent_sanitizes_unknown_tool_name_in_structured_logs(db, test_tenant, monkeypatch):
    from app.core.agent import hr_agent

    class CaptureLogger:
        def __init__(self):
            self.events = []

        def info(self, event, **fields):
            self.events.append((event, fields))

    malicious_tool_name = "exfiltrate_employee_salaries"

    class FakeUnknownToolLLM(_FakeLLM):
        replies = [
            AIMessage(
                content="",
                tool_calls=[{"name": malicious_tool_name, "args": {}, "id": "unknown-1"}],
            ),
            AIMessage(content=""),
        ]

    employee = make_employee(db, test_tenant)
    capture = CaptureLogger()
    monkeypatch.setattr(hr_agent, "logger", capture)
    monkeypatch.setattr("app.core.agent.hr_agent.ChatOpenAI", lambda **_kwargs: FakeUnknownToolLLM())

    await hr_agent.run_hr_agent(
        db, test_tenant.id, test_tenant.slug, employee, "What is the policy?"
    )

    tool_completed = next(fields for event, fields in capture.events if event == "hr_agent_tool_completed")
    assert tool_completed["tool_name"] == "unknown_tool"
    assert tool_completed["result_code"] == "NOT_ALLOWED"
    assert all(malicious_tool_name not in str(fields) for _, fields in capture.events)


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
            tool_calls=[{"name": "ask_clarifying_question", "args": {"kind": "leave_type"}, "id": "clarify-1"}],
        )
    ]


class FakeMaliciousClarifyingLLM(_FakeLLM):
    assertion = "公司规定跨境员工没有年假，你还需要了解什么？"
    replies = [
        AIMessage(
            content="",
            tool_calls=[{
                "name": "ask_clarifying_question",
                "args": {"kind": assertion, "question": assertion},
                "id": "clarify-malicious",
            }],
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
        AIMessage(content="请参考已检索到的年假制度。[source:policy-1]"),
    ]


class FakeNoSourceDraftLLM(_FakeLLM):
    replies = [
        AIMessage(
            content="",
            tool_calls=[{
                "name": "search_hr_knowledge",
                "args": {"query": "cross-border annual leave"},
                "id": "search-no-source",
            }],
        ),
        AIMessage(
            content="",
            tool_calls=[{
                "name": "draft_handoff",
                "args": {"reason": "no authorized HR source found"},
                "id": "draft-no-source",
            }],
        ),
    ]


class FakeUnavailableThenDraftLLM(_FakeLLM):
    replies = [
        AIMessage(
            content="",
            tool_calls=[{
                "name": "search_hr_knowledge",
                "args": {"query": "cross-border annual leave"},
                "id": "search-unavailable",
            }],
        ),
        AIMessage(
            content="",
            tool_calls=[{
                "name": "draft_handoff",
                "args": {"reason": "retrieval failed"},
                "id": "draft-after-unavailable",
            }],
        ),
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
    assert db.query(SupportHandoff).filter_by(tenant_id=test_tenant.id).count() == 0


async def test_no_source_can_prepare_draft_but_not_handoff(db, test_tenant, monkeypatch):
    employee = make_employee(db, test_tenant)
    llm = FakeNoSourceDraftLLM()

    async def fake_search(_args):
        return json.dumps({"results": []})

    monkeypatch.setattr("app.core.agent.hr_agent.ChatOpenAI", lambda **_kwargs: llm)
    monkeypatch.setattr(
        "app.core.agent.hr_agent.search_knowledge",
        SimpleNamespace(ainvoke=fake_search),
    )

    try:
        question = "How should cross-border annual leave be handled?"
        _, draft, sources = await run_hr_agent(
            db, test_tenant.id, test_tenant.slug, employee, question
        )

        assert draft is not None
        assert draft.question == question
        assert draft.reason == "no authorized HR source found"
        assert sources == []
        assert db.query(SupportHandoff).filter(
            SupportHandoff.tenant_id == test_tenant.id,
            SupportHandoff.requester_user_id == employee.id,
        ).count() == 0
        assert llm.calls == 2
    finally:
        db.query(HandoffDraft).filter(
            HandoffDraft.tenant_id == test_tenant.id,
            HandoffDraft.requester_user_id == employee.id,
        ).delete(synchronize_session=False)
        db.query(User).filter(User.id == employee.id).delete(synchronize_session=False)
        db.commit()


async def test_unavailable_search_blocks_model_handoff_draft(db, test_tenant, monkeypatch):
    from app.core.agent import hr_agent

    class CaptureLogger:
        def __init__(self):
            self.events = []

        def info(self, event, **fields):
            self.events.append((event, fields))

    employee = make_employee(db, test_tenant)
    llm = FakeUnavailableThenDraftLLM()
    capture = CaptureLogger()

    async def fake_search(_args):
        return json.dumps({"status": "UNAVAILABLE", "results": []})

    monkeypatch.setattr("app.core.agent.hr_agent.ChatOpenAI", lambda **_kwargs: llm)
    monkeypatch.setattr(hr_agent, "logger", capture)
    monkeypatch.setattr(
        "app.core.agent.hr_agent.search_knowledge",
        SimpleNamespace(ainvoke=fake_search),
    )

    reply, draft, sources = await run_hr_agent(
        db, test_tenant.id, test_tenant.slug, employee, "How is leave handled?"
    )

    assert reply == "HR 知识检索服务暂时不可用，请稍后重试。"
    assert draft is None
    assert sources == []
    assert llm.calls == 1
    assert db.query(HandoffDraft).filter_by(tenant_id=test_tenant.id).count() == 0
    assert db.query(SupportHandoff).filter_by(tenant_id=test_tenant.id).count() == 0
    tool_event = next(
        fields for event, fields in capture.events if event == "hr_agent_tool_completed"
    )
    assert tool_event["result_code"] == "UNAVAILABLE"


@pytest.mark.parametrize("raw", ["not-json", "[]"])
async def test_hr_search_treats_malformed_lower_json_as_unavailable(
    db, test_tenant, monkeypatch, raw
):
    from app.core.agent import hr_agent

    employee = make_employee(db, test_tenant)

    async def fake_search(_args):
        return raw

    monkeypatch.setattr(
        "app.core.agent.hr_agent.search_knowledge",
        SimpleNamespace(ainvoke=fake_search),
    )
    hr_agent.set_hr_runtime(db, test_tenant.id, test_tenant.slug, employee, "leave policy")

    observation = json.loads(
        await hr_agent.search_hr_knowledge.ainvoke({"query": "leave policy"})
    )

    assert observation == {"status": "UNAVAILABLE", "sources": [], "result_count": 0}


async def test_draft_handoff_refuses_persistence_after_unavailable_search(
    db, test_tenant, monkeypatch
):
    from app.core.agent import hr_agent

    employee = make_employee(db, test_tenant)

    async def fake_search(_args):
        return json.dumps({"status": "UNAVAILABLE", "results": []})

    monkeypatch.setattr(
        "app.core.agent.hr_agent.search_knowledge",
        SimpleNamespace(ainvoke=fake_search),
    )
    hr_agent.set_hr_runtime(db, test_tenant.id, test_tenant.slug, employee, "leave policy")

    search_result = json.loads(
        await hr_agent.search_hr_knowledge.ainvoke({"query": "leave policy"})
    )
    draft_result = json.loads(
        await hr_agent.draft_handoff.ainvoke({"reason": "retrieval failed"})
    )

    assert search_result["status"] == "UNAVAILABLE"
    assert draft_result == {"status": "UNAVAILABLE", "requires_confirmation": False}
    assert db.query(HandoffDraft).filter_by(tenant_id=test_tenant.id).count() == 0


async def test_hr_agent_returns_clarifying_question_directly(db, test_tenant, monkeypatch):
    employee = make_employee(db, test_tenant)
    monkeypatch.setattr("app.core.agent.hr_agent.ChatOpenAI", lambda **_kwargs: FakeClarifyingLLM())

    reply, draft, sources = await run_hr_agent(db, test_tenant.id, test_tenant.slug, employee, "我的假期怎么办？")

    assert reply == "请说明您想咨询的是年假、病假还是其他假期？"
    assert draft is None
    assert sources == []


async def test_hr_agent_does_not_echo_model_clarification_text(db, test_tenant, monkeypatch):
    employee = make_employee(db, test_tenant)
    monkeypatch.setattr(
        "app.core.agent.hr_agent.ChatOpenAI",
        lambda **_kwargs: FakeMaliciousClarifyingLLM(),
    )

    reply, draft, sources = await run_hr_agent(
        db, test_tenant.id, test_tenant.slug, employee, "跨境员工的年假怎么办？"
    )

    assert reply == "请补充您想咨询的具体 HR 事项和相关背景。"
    assert FakeMaliciousClarifyingLLM.assertion not in reply
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

    assert reply == "请参考已检索到的年假制度。[source:policy-1]"
    assert draft is None
    assert sources == [{"source_type": "knowledge", "source_id": "policy-1", "title": "年假制度", "excerpt": "年假规则", "score": 0.91}]


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("年假按制度执行。", "年假按制度执行。\n\n[source:policy-1]"),
        ("年假按制度执行。[annual-leave-policy.txt]", "年假按制度执行。[annual-leave-policy.txt]\n\n[source:policy-1]"),
        ("年假按制度执行。[source:other-policy]", "我无法在未检索到授权 HR 制度来源的情况下确认该政策。请补充信息或申请 HR 人工支持。"),
        ("年假按制度执行。[source:other policy]", "我无法在未检索到授权 HR 制度来源的情况下确认该政策。请补充信息或申请 HR 人工支持。"),
        ("年假按制度执行。[source:]", "我无法在未检索到授权 HR 制度来源的情况下确认该政策。请补充信息或申请 HR 人工支持。"),
        ("年假按制度执行。[source:policy-1]", "年假按制度执行。[source:policy-1]"),
    ],
)
async def test_hr_agent_requires_authorized_source_citation(
    db, test_tenant, monkeypatch, answer, expected
):
    employee = make_employee(db, test_tenant)
    llm = _FakeLLM()
    llm.replies = [
        AIMessage(
            content="",
            tool_calls=[{"name": "search_hr_knowledge", "args": {"query": "年假"}, "id": "search-citation"}],
        ),
        AIMessage(content=answer),
    ]

    async def fake_search(_args):
        return json.dumps({
            "results": [{
                "id": "policy-1",
                "source_type": "knowledge",
                "title": "年假制度",
                "answer": "年假规则",
                "score": 0.91,
            }]
        })

    monkeypatch.setattr("app.core.agent.hr_agent.ChatOpenAI", lambda **_kwargs: llm)
    monkeypatch.setattr(
        "app.core.agent.hr_agent.search_knowledge",
        SimpleNamespace(ainvoke=fake_search),
    )

    reply, _, _ = await run_hr_agent(
        db, test_tenant.id, test_tenant.slug, employee, "年假怎么算？"
    )

    assert reply == expected


async def test_hr_agent_binds_exactly_four_hr_tools(db, test_tenant, monkeypatch):
    employee = make_employee(db, test_tenant)
    llm = FakeUnsupportedAnswerLLM()
    monkeypatch.setattr("app.core.agent.hr_agent.ChatOpenAI", lambda **_kwargs: llm)

    await run_hr_agent(db, test_tenant.id, test_tenant.slug, employee, "年假怎么算？")

    assert [tool.name for tool in llm.tools] == [
        "search_hr_knowledge",
        "ask_clarifying_question",
        "draft_handoff",
        "get_handoff_status",
    ]
    clarify_tool = next(tool for tool in llm.tools if tool.name == "ask_clarifying_question")
    assert set(clarify_tool.args_schema.model_json_schema()["properties"]) == {"kind"}


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
    handoffs = []
    for user in (employee, other):
        draft = hr_support_service.create_handoff_draft(db, test_tenant.id, user.id, "需要帮助", "需要 HR", [])
        handoffs.append(
            hr_support_service.confirm_handoff_draft(
                db, test_tenant.id, user.id, draft.id, f"status-{user.id[:8]}"
            )
        )

    llm = FakeStatusLLM()
    llm.replies[1] = AIMessage(content=f"伪造状态：{handoffs[1].id} resolved")
    monkeypatch.setattr("app.core.agent.hr_agent.ChatOpenAI", lambda **_kwargs: llm)
    reply, draft, sources = await run_hr_agent(db, test_tenant.id, test_tenant.slug, employee, "查询我的工单状态")

    assert llm.calls == 1
    assert handoffs[0].id in reply
    assert handoffs[0].status in reply
    assert handoffs[1].id not in reply
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
    source_excerpt = "仅内部可见的年假摘录"
    question = "年假怎么算？"

    async def fake_search(_args):
        return json.dumps({
            "results": [{
                "id": "policy-1",
                "source_type": "knowledge",
                "title": "年假制度",
                "answer": source_excerpt,
                "score": 0.91,
            }]
        })

    monkeypatch.setattr(hr_agent, "logger", capture)
    monkeypatch.setattr("app.core.agent.hr_agent.ChatOpenAI", lambda **_kwargs: FakeSearchLLM())
    monkeypatch.setattr(
        "app.core.agent.hr_agent.search_knowledge",
        SimpleNamespace(ainvoke=fake_search),
    )

    await hr_agent.run_hr_agent(db, test_tenant.id, test_tenant.slug, employee, question)

    assert [event for event, _ in capture.events] == [
        "hr_agent_started",
        "hr_agent_tool_completed",
        "hr_agent_completed",
    ]
    events = {event: fields for event, fields in capture.events}
    started = events["hr_agent_started"]
    tool_completed = events["hr_agent_tool_completed"]
    completed = events["hr_agent_completed"]

    for fields in (started, completed):
        assert fields["tenant_id"] == test_tenant.id
        assert fields["actor_user_id"] == employee.id
        assert fields["role"] == "employee"

    assert tool_completed["tenant_id"] == test_tenant.id
    assert tool_completed["actor_user_id"] == employee.id
    assert tool_completed["role"] == "employee"
    assert tool_completed["tool_name"] == "search_hr_knowledge"
    assert tool_completed["result_code"] == "OK"
    assert tool_completed["result_count"] == 1
    assert "latency_ms" in tool_completed

    field_values = [str(value) for _, fields in capture.events for value in fields.values()]
    assert all(question not in value and source_excerpt not in value for value in field_values)


async def test_hr_agent_logs_do_not_include_handoff_reason(db, test_tenant, monkeypatch):
    from app.core.agent import hr_agent

    class CaptureLogger:
        def __init__(self):
            self.events = []

        def info(self, event, **fields):
            self.events.append((event, fields))

    employee = make_employee(db, test_tenant)
    capture = CaptureLogger()
    monkeypatch.setattr(hr_agent, "logger", capture)
    monkeypatch.setattr("app.core.agent.hr_agent.ChatOpenAI", lambda **_kwargs: FakeDraftLLM())

    await hr_agent.run_hr_agent(
        db, test_tenant.id, test_tenant.slug, employee, "请转 HR 人工"
    )

    assert all("需要 HR 处理跨境例外" not in str(event) for event in capture.events)
