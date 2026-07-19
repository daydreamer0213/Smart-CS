"""Observability tests for the role-scoped enterprise agent."""

import json

from langchain_core.messages import AIMessage

from app.core.agent.business_agent import run_business_agent
from app.core.agent.hr_agent import _normalize_sources
from app.core.auth.security import hash_password
from app.models.user import User
from app.schemas.hr_support import SourceCitation


class CaptureLogger:
    def __init__(self):
        self.events = []

    def info(self, event, **fields):
        self.events.append(("info", event, fields))

    def warning(self, event, **fields):
        self.events.append(("warning", event, fields))


def test_hr_source_normalization_keeps_optional_document_provenance():
    sources = _normalize_sources({"results": [
        {
            "id": "document-chunk-1",
            "source_type": "document",
            "title": "leave-policy.pdf",
            "content": "Annual leave policy.",
            "score": 0.91,
            "page_start": 4,
            "page_end": 5,
            "section_path": ["HR", "Leave"],
            "element_types": ["paragraph", "table"],
        },
        {
            "id": "legacy-knowledge-1",
            "source_type": "knowledge",
            "title": "Legacy FAQ",
            "answer": "Legacy answer.",
        },
    ]})

    assert sources == [
        {
            "source_type": "document",
            "source_id": "document-chunk-1",
            "title": "leave-policy.pdf",
            "excerpt": "Annual leave policy.",
            "score": 0.91,
            "page_start": 4,
            "page_end": 5,
            "section_path": ["HR", "Leave"],
            "element_types": ["paragraph", "table"],
        },
        {
            "source_type": "knowledge",
            "source_id": "legacy-knowledge-1",
            "title": "Legacy FAQ",
            "excerpt": "Legacy answer.",
            "score": None,
        },
    ]
    document_citation = SourceCitation(**sources[0])
    legacy_citation = SourceCitation(**sources[1])
    assert document_citation.model_dump() == sources[0]
    assert json.loads(document_citation.model_dump_json()) == sources[0]
    assert legacy_citation.model_dump() == sources[1]
    assert json.loads(legacy_citation.model_dump_json()) == sources[1]


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
