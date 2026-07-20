"""Run a local SmartCS HR Agent lifecycle demo.

Start the API first:
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

Then run:
    python scripts/demo_enterprise_flow.py
"""

from __future__ import annotations

import json
import os
import random
import secrets
import string
import sys
import time
import urllib.error
import urllib.request


BASE_URL = os.getenv("SMARTCS_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


class DemoFailure(RuntimeError):
    pass


def _suffix() -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(6))


def _demo_password() -> str:
    return secrets.token_urlsafe(24)


def _request(method: str, path: str, *, token: str | None = None, json_body=None, data=None, headers=None):
    request_headers = dict(headers or {})
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    if token:
        request_headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"detail": raw}
        return exc.code, body


def _multipart_file(
    field_name: str,
    filename: str,
    content: bytes,
    content_type: str,
    *,
    fields: list[tuple[str, str]] = (),
) -> tuple[bytes, dict[str, str]]:
    boundary = f"----smartcs-demo-{_suffix()}"
    parts = []
    for name, value in fields:
        parts.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode("utf-8"),
            b"\r\n",
        ])
    parts.extend([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode(),
        f"Content-Type: {content_type}\r\n\r\n".encode(),
        content,
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    return b"".join(parts), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def _require(status: int, expected: set[int], label: str) -> None:
    if status not in expected:
        raise DemoFailure(f"{label} failed: expected {sorted(expected)}, got {status}")


def _require_live_chat(status: int, label: str) -> None:
    if status == 503:
        raise DemoFailure(
            f"{label} cannot call the configured LLM. Check LLM_API_KEY, "
            "LLM_BASE_URL, LLM_MODEL, network access, and provider quota."
        )
    _require(status, {200}, label)


def _require_cited_answer(chat: dict) -> None:
    if not (chat.get("sources") or []) or "[source:" not in str(chat.get("reply") or ""):
        raise DemoFailure("policy answer did not contain an authorized source citation")


def _require_pending_draft(chat: dict) -> str:
    draft = chat.get("pending_handoff") or {}
    if draft.get("status") != "pending" or not draft.get("id"):
        raise DemoFailure("exception request did not create a pending HR handoff draft")
    return str(draft["id"])


def _print_step(title: str) -> None:
    print(f"\n== {title} ==")


def _show_summary(**values) -> None:
    print(json.dumps(values, ensure_ascii=False))


def main() -> int:
    suffix = _suffix()
    slug = f"beichen-hr-{suffix}"
    password = _demo_password()

    _print_step("Health")
    status, _ = _request("GET", "/health")
    _require(status, {200}, "health")
    _show_summary(status=status)

    _print_step("Create HR tenant and users")
    status, owner = _request(
        "POST",
        "/api/v1/auth/register",
        json_body={
            "role": "owner",
            "tenant_slug": slug,
            "tenant_name": "Beichen Technology HR",
            "email": f"owner-{suffix}@example.com",
            "password": password,
            "display_name": "HR Owner",
        },
    )
    _require(status, {201}, "owner register")
    owner_token = owner["access_token"]

    status, admin = _request(
        "POST",
        "/api/v1/auth/register",
        token=owner_token,
        json_body={
            "role": "admin",
            "tenant_slug": slug,
            "email": f"hr-admin-{suffix}@example.com",
            "password": password,
            "display_name": "HR Admin",
        },
    )
    _require(status, {201}, "HR admin register")

    status, employee = _request(
        "POST",
        "/api/v1/auth/register",
        token=owner_token,
        json_body={
            "role": "employee",
            "tenant_slug": slug,
            "email": f"employee-{suffix}@example.com",
            "password": password,
            "display_name": "Employee",
        },
    )
    _require(status, {201}, "employee register")
    employee_token = employee["access_token"]
    admin_token = admin["access_token"]
    admin_id = admin["user"]["id"]
    _show_summary(tenant_slug=slug, status="ready")

    _print_step("Upload employee-visible annual leave policy")
    upload_body, headers = _multipart_file(
        "file",
        "beichen-annual-leave-policy.txt",
        "北辰科技年假制度：全职员工工作满一年后享有 5 个工作日年假，至少提前 3 个工作日申请。".encode("utf-8"),
        "text/plain",
        fields=[("audience_roles", "employee")],
    )
    status, document = _request(
        "POST",
        f"/api/v1/admin/{slug}/documents/upload",
        token=owner_token,
        data=upload_body,
        headers=headers,
    )
    _require(status, {201}, "document upload")
    if document.get("status") != "ready" or not document.get("document_id"):
        raise DemoFailure("document upload did not finish in ready state")
    if document.get("review_status") != "pending_review":
        raise DemoFailure("document upload did not enter pending review")
    document_id = str(document["document_id"])
    _show_summary(
        document_id=document_id,
        family_id=document.get("family_id"),
        version=document.get("version"),
        index_generation=document.get("index_generation"),
        review_status=document.get("review_status"),
        status=document["status"],
    )

    _print_step("Approve and publish the governed policy")
    status, reviewed = _request(
        "POST",
        f"/api/v1/admin/{slug}/documents/{document_id}/review",
        token=owner_token,
        json_body={"decision": "approved"},
    )
    _require(status, {200}, "document review")
    if reviewed.get("review_status") != "approved" or not reviewed.get("is_current"):
        raise DemoFailure("document review did not publish the approved snapshot")
    _show_summary(
        document_id=document_id,
        family_id=reviewed.get("family_id"),
        review_status=reviewed.get("review_status"),
        is_current=reviewed.get("is_current"),
    )

    session_id = f"demo-session-{int(time.time())}"
    _print_step("Employee asks a cited policy question")
    status, policy_chat = _request(
        "POST",
        f"/api/v1/{slug}/assistant/chat",
        token=employee_token,
        json_body={"session_id": session_id, "message": "北辰科技年假如何计算？"},
    )
    _require_live_chat(status, "policy question")
    _require_cited_answer(policy_chat)
    citation_fields = (
        "source_type",
        "source_id",
        "title",
        "page_start",
        "page_end",
        "section_path",
        "element_types",
    )
    safe_sources = [
        {
            field: source[field]
            for field in citation_fields
            if field in source and source[field] is not None
        }
        for source in policy_chat.get("sources", [])
    ]
    _show_summary(reply=policy_chat.get("reply"), sources=safe_sources, status="cited")

    _print_step("Reindex the current policy without service interruption")
    status, rebuilt = _request(
        "POST",
        f"/api/v1/admin/{slug}/documents/{document_id}/reindex",
        token=owner_token,
    )
    _require(status, {200}, "document reindex")
    if rebuilt.get("status") != "ready" or not rebuilt.get("is_current"):
        raise DemoFailure("document reindex did not publish the new generation")
    _show_summary(
        document_id=rebuilt.get("document_id"),
        family_id=rebuilt.get("family_id"),
        version=rebuilt.get("version"),
        index_generation=rebuilt.get("index_generation"),
        status=rebuilt.get("status"),
        is_current=rebuilt.get("is_current"),
    )

    _print_step("Employee requests an overseas assignment exception")
    status, exception_chat = _request(
        "POST",
        f"/api/v1/{slug}/assistant/chat",
        token=employee_token,
        json_body={
            "session_id": session_id,
            "message": "我在海外派驻期间需要申请年假例外，请转 HR 人工处理。",
        },
    )
    _require_live_chat(status, "exception request")
    draft_id = _require_pending_draft(exception_chat)
    _show_summary(draft_id=draft_id, status="pending")

    _print_step("Employee confirms the HR handoff")
    status, handoff = _request(
        "POST",
        f"/api/v1/{slug}/hr-support/drafts/{draft_id}/confirm",
        token=employee_token,
        headers={"Idempotency-Key": f"demo-confirm-{suffix}"},
    )
    _require(status, {200}, "handoff confirmation")
    if handoff.get("status") != "open" or not handoff.get("id"):
        raise DemoFailure("handoff confirmation did not create an open official handoff")
    handoff_id = str(handoff["id"])
    _show_summary(handoff_id=handoff_id, status=handoff["status"])

    _print_step("HR admin assigns and resolves the handoff")
    status, handoffs = _request("GET", f"/api/v1/{slug}/hr-support/admin", token=admin_token)
    _require(status, {200}, "admin handoff list")
    if not any(item.get("id") == handoff_id for item in handoffs):
        raise DemoFailure("official handoff is missing from the HR admin queue")

    status, assigned = _request(
        "PATCH",
        f"/api/v1/{slug}/hr-support/admin/{handoff_id}",
        token=admin_token,
        json_body={"status": "assigned", "assigned_user_id": admin_id},
    )
    _require(status, {200}, "assign handoff")
    if assigned.get("status") != "assigned":
        raise DemoFailure("handoff assignment did not reach assigned state")

    status, resolved = _request(
        "PATCH",
        f"/api/v1/{slug}/hr-support/admin/{handoff_id}",
        token=admin_token,
        json_body={"status": "resolved", "resolution_note": "已由 HR 核验：海外派驻例外需人工审核。"},
    )
    _require(status, {200}, "resolve handoff")
    if resolved.get("status") != "resolved":
        raise DemoFailure("handoff resolution did not reach resolved state")
    _show_summary(handoff_id=handoff_id, status=resolved["status"])

    _print_step("Employee verifies own handoff status")
    status, my_handoffs = _request("GET", f"/api/v1/{slug}/hr-support/me", token=employee_token)
    _require(status, {200}, "employee handoff list")
    if not any(item.get("id") == handoff_id and item.get("status") == "resolved" for item in my_handoffs):
        raise DemoFailure("employee cannot see the resolved official handoff")
    _show_summary(handoff_id=handoff_id, status="resolved")

    _print_step("Verify tenant isolation")
    other_slug = f"{slug}-other"
    status, _ = _request(
        "POST",
        "/api/v1/auth/register",
        json_body={
            "role": "owner",
            "tenant_slug": other_slug,
            "tenant_name": "Other HR Tenant",
            "email": f"other-{suffix}@example.com",
            "password": password,
            "display_name": "Other Owner",
        },
    )
    _require(status, {201}, "other tenant register")
    status, _ = _request("GET", f"/api/v1/{other_slug}/hr-support/me", token=employee_token)
    _require(status, {403}, "cross-tenant access")
    _show_summary(status="tenant_access_denied")

    print("\nLive HR Agent demo complete.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DemoFailure as exc:
        print(f"Live HR Agent demo failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except urllib.error.URLError as exc:
        print(f"Cannot reach SmartCS at {BASE_URL}: {exc}", file=sys.stderr)
        raise SystemExit(1)
