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
            return 201, {"document_id": "doc-1", "status": "ready", "chunk_count": 1}
        if path.endswith("/assistant/chat"):
            return 503, {"detail": "Assistant model is not configured"}
        raise AssertionError(f"unexpected request: {method} {path}")

    monkeypatch.setattr(demo, "_request", fake_request)

    with pytest.raises(demo.DemoFailure, match="LLM"):
        demo.main()


def test_live_demo_executes_the_hr_handoff_lifecycle(monkeypatch):
    calls = []
    registrations = iter([
        {"access_token": "owner-token", "user": {"id": "owner-1"}},
        {"access_token": "admin-token", "user": {"id": "admin-1"}},
        {"access_token": "employee-token", "user": {"id": "employee-1"}},
        {"access_token": "other-token", "user": {"id": "other-owner-1"}},
    ])
    chats = iter([
        {"reply": "年假制度说明 [source:doc-1]", "sources": [{"source_id": "doc-1"}], "pending_handoff": None},
        {"reply": "已准备待确认的 HR 支持请求", "sources": [{"source_id": "doc-1"}], "pending_handoff": {"id": "draft-1", "status": "pending"}},
    ])

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path == "/health":
            return 200, {"status": "ok"}
        if path == "/api/v1/auth/register":
            return 201, next(registrations)
        if path.endswith("/documents/upload"):
            return 201, {"document_id": "doc-1", "status": "ready", "chunk_count": 1}
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
    assert any(path.endswith("/assistant/chat") for path in paths)
    assert any(path.endswith("/drafts/draft-1/confirm") for path in paths)
    assert any(path.endswith("/hr-support/admin/handoff-1") for path in paths)
    assert any(path.endswith("/hr-support/me") for path in paths)
