import json
import secrets

import pytest

from scripts import demo_enterprise_flow as demo


def test_multipart_file_encodes_repeated_audience_roles():
    body, headers = demo._multipart_file(
        "file",
        "annual-leave-policy.txt",
        b"fictional policy",
        "text/plain",
        fields=[("audience_roles", "employee"), ("audience_roles", "admin")],
    )

    assert headers["Content-Type"].startswith("multipart/form-data; boundary=")
    assert body.count(b'name="audience_roles"') == 2
    assert b"employee" in body
    assert b"admin" in body


def test_live_demo_stops_when_assistant_model_is_unavailable(monkeypatch):
    monkeypatch.setattr(demo, "_suffix", lambda: "fixed01")

    def fake_request(method, path, **_kwargs):
        if path == "/health":
            return 200, {"status": "ok"}
        if path == "/api/v1/auth/register":
            return 201, {"access_token": "redacted", "user": {"id": "user-1"}}
        if path.endswith("/documents/upload"):
            return 201, {
                "document_id": "doc-1",
                "family_id": "family-1",
                "version": 1,
                "index_generation": 1,
                "review_status": "pending_review",
                "status": "ready",
                "chunk_count": 1,
            }
        if path.endswith("/documents/doc-1/review"):
            return 200, {
                "document_id": "doc-1",
                "review_status": "approved",
                "is_current": True,
            }
        if path.endswith("/assistant/chat"):
            return 503, {"detail": "Assistant model is not configured"}
        raise AssertionError(f"unexpected request: {method} {path}")

    monkeypatch.setattr(demo, "_request", fake_request)

    with pytest.raises(demo.DemoFailure, match="LLM"):
        demo.main()


def test_live_demo_executes_the_hr_handoff_lifecycle(monkeypatch, capsys):
    calls = []
    monkeypatch.setenv("SMARTCS_DEMO_PASSWORD", "ignored-by-script")
    monkeypatch.setattr(secrets, "token_urlsafe", lambda _size: "generated-at-runtime")
    registrations = iter([
        {"access_token": "owner-token", "user": {"id": "owner-1"}},
        {"access_token": "admin-token", "user": {"id": "admin-1"}},
        {"access_token": "employee-token", "user": {"id": "employee-1"}},
        {"access_token": "other-token", "user": {"id": "other-owner-1"}},
    ])
    chats = iter([
        {
            "reply": "年假制度说明 [source:doc-1]",
            "display_reply": "年假制度说明 来源：《北辰科技年假制度》",
            "sources": [{"source_id": "doc-1"}],
            "pending_handoff": None,
        },
        {"reply": "已准备待确认的 HR 支持请求", "sources": [{"source_id": "doc-1"}], "pending_handoff": {"id": "draft-1", "status": "pending"}},
    ])

    chats = list(chats)
    chats[0]["sources"].append({
        "source_id": "doc-1",
        "title": None,
        "page_start": None,
    })
    chats[0]["sources"][0].update({
        "source_type": "document",
        "title": "北辰科技年假制度",
        "excerpt": "must-not-be-exported",
        "score": 0.91,
        "page_start": 2,
        "page_end": 2,
        "section_path": ["Annual Leave"],
        "element_types": ["paragraph"],
        "token": "must-not-be-exported",
        "storage_key": "must-not-be-exported",
        "path": "D:\\DevData\\smartcs\\private.pdf",
    })
    chats = iter(chats)

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path == "/health":
            return 200, {"status": "ok"}
        if path == "/api/v1/auth/register":
            assert kwargs["json_body"]["password"] == "generated-at-runtime"
            return 201, next(registrations)
        if path.endswith("/documents/upload"):
            assert b'name="family_name"' in kwargs["data"]
            assert "北辰科技年假制度".encode("utf-8") in kwargs["data"]
            return 201, {
                "document_id": "doc-1",
                "family_id": "family-1",
                "version": 1,
                "index_generation": 1,
                "review_status": "pending_review",
                "status": "ready",
                "chunk_count": 1,
            }
        if path.endswith("/documents/doc-1/review"):
            assert kwargs["json_body"] == {"decision": "approved"}
            return 200, {
                "document_id": "doc-1",
                "family_id": "family-1",
                "review_status": "approved",
                "reviewed_by_user_id": "owner-1",
                "is_current": True,
            }
        if path.endswith("/documents/doc-1/reindex"):
            return 200, {
                "document_id": "doc-2",
                "source_document_id": "doc-1",
                "family_id": "family-1",
                "version": 1,
                "index_generation": 2,
                "status": "ready",
                "error_message": None,
                "is_current": True,
            }
        if path.endswith("/assistant/chat"):
            return 200, next(chats)
        if path.endswith("/drafts/draft-1/confirm"):
            assert kwargs["headers"]["Idempotency-Key"].startswith("demo-confirm-")
            return 200, {"id": "handoff-1", "status": "open"}
        if path.endswith("/hr-support/admin"):
            return 200, [{"id": "handoff-1", "status": "open"}]
        if path.endswith("/hr-support/admin/handoff-1"):
            return 200, {"id": "handoff-1", "status": kwargs["json_body"]["status"]}
        if path.endswith("/hr-support/me") and "-other/" not in path:
            return 200, [{"id": "handoff-1", "status": "resolved"}]
        if path.endswith("/hr-support/me") and "-other/" in path:
            return 403, {"detail": {"code": "TENANT_MISMATCH"}}
        raise AssertionError(f"unexpected request: {method} {path}")

    monkeypatch.setattr(demo, "_suffix", lambda: "fixed01")
    monkeypatch.setattr(demo, "_request", fake_request)

    assert demo.main() == 0
    paths = [path for _method, path, _kwargs in calls]
    review_index = next(
        index for index, path in enumerate(paths)
        if path.endswith("/documents/doc-1/review")
    )
    chat_index = next(
        index for index, path in enumerate(paths)
        if path.endswith("/assistant/chat")
    )
    reindex_index = next(
        index for index, path in enumerate(paths)
        if path.endswith("/documents/doc-1/reindex")
    )
    assert review_index < chat_index < reindex_index
    assert any(path.endswith("/drafts/draft-1/confirm") for path in paths)
    assert any(path.endswith("/hr-support/admin/handoff-1") for path in paths)
    assert any(path.endswith("/hr-support/me") for path in paths)
    assert demo._demo_password() == "generated-at-runtime"
    output = capsys.readouterr().out
    summaries = [
        json.loads(line)
        for line in output.splitlines()
        if line.startswith("{")
    ]
    handoff_statuses = [
        summary["status"]
        for summary in summaries
        if summary.get("handoff_id") == "handoff-1"
    ]
    assert handoff_statuses == ["open", "assigned", "resolved", "resolved"]

    def collect_strings(value):
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            value = value.values()
        elif not isinstance(value, list):
            return []
        return [item for nested in value for item in collect_strings(nested)]

    cited_summary = next(summary for summary in summaries if summary.get("status") == "cited")
    assert cited_summary["display_reply"] == "年假制度说明 来源：《北辰科技年假制度》"
    assert "[source:doc-1]" not in cited_summary["display_reply"]
    assert cited_summary["sources"][1] == {"source_id": "doc-1"}
    assert '"display_reply":' in output
    assert '"source_type": "document"' in output
    assert '"source_id": "doc-1"' in output
    assert '"title": "北辰科技年假制度"' in output
    assert '"page_start": 2' in output
    assert '"page_end": 2' in output
    assert '"section_path": ["Annual Leave"]' in output
    assert '"element_types": ["paragraph"]' in output
    assert '"excerpt"' not in output
    assert '"path"' not in output
    assert "must-not-be-exported" not in output
    assert '"score"' not in output
    assert '"token"' not in output
    assert "owner-token" not in output
    assert "admin-token" not in output
    assert "employee-token" not in output
    assert "other-token" not in output
    assert '"access_token"' not in output
    assert "storage_key" not in output
    assert "D:\\DevData\\smartcs\\private.pdf" not in collect_strings(summaries)
