"""Run a local SmartCS enterprise-flow demo.

Start the API first:
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

Then run:
    python scripts/demo_enterprise_flow.py
"""

from __future__ import annotations

import json
import os
import random
import string
import sys
import time
import urllib.error
import urllib.request


BASE_URL = os.getenv("SMARTCS_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def _suffix() -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(6))


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


def _multipart_file(field_name: str, filename: str, content: bytes, content_type: str):
    boundary = f"----smartcs-demo-{_suffix()}"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            (
                f'Content-Disposition: form-data; name="{field_name}"; '
                f'filename="{filename}"\r\n'
            ).encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            content,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    return body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def _print_step(title: str):
    print(f"\n== {title} ==")


def _show(status: int, body):
    print(f"status: {status}")
    print(json.dumps(body, ensure_ascii=False, indent=2)[:2000])


def _show_summary(status: int, body):
    print(f"status: {status}")
    print(json.dumps(body, ensure_ascii=False, indent=2))


def _expect(status: int, expected: set[int], label: str):
    if status not in expected:
        raise SystemExit(f"{label} failed: expected {sorted(expected)}, got {status}")


def main() -> int:
    slug = os.getenv("SMARTCS_DEMO_TENANT", f"demo-{_suffix()}")
    password = os.getenv("SMARTCS_DEMO_PASSWORD", "Password123")
    owner_email = f"owner-{_suffix()}@example.com"
    agent_email = f"agent-{_suffix()}@example.com"
    employee_email = f"employee-{_suffix()}@example.com"

    _print_step("Health")
    status, body = _request("GET", "/health")
    _show(status, body)
    _expect(status, {200}, "health")

    _print_step("Owner registers a tenant")
    status, owner = _request(
        "POST",
        "/api/v1/auth/register",
        json_body={
            "role": "owner",
            "tenant_slug": slug,
            "tenant_name": "Demo Tenant",
            "email": owner_email,
            "password": password,
            "display_name": "Demo Owner",
        },
    )
    _show(status, {"tenant_slug": slug, "owner_email": owner_email, "created": status == 201})
    _expect(status, {201}, "owner register")
    owner_token = owner["access_token"]

    _print_step("Owner creates an agent user")
    status, agent = _request(
        "POST",
        "/api/v1/auth/register",
        token=owner_token,
        json_body={
            "role": "agent",
            "tenant_slug": slug,
            "email": agent_email,
            "password": password,
            "display_name": "Demo Agent",
        },
    )
    _show(status, {"agent_email": agent_email, "created": status == 201})
    _expect(status, {201}, "agent register")
    agent_token = agent["access_token"]

    _print_step("Owner creates a knowledge-only employee")
    status, employee = _request(
        "POST",
        "/api/v1/auth/register",
        token=owner_token,
        json_body={
            "role": "employee",
            "tenant_slug": slug,
            "email": employee_email,
            "password": password,
            "display_name": "Demo Employee",
        },
    )
    _show(status, {"employee_email": employee_email, "created": status == 201})
    _expect(status, {201}, "employee register")
    employee_token = employee["access_token"]

    _print_step("Agent is blocked from admin APIs")
    status, body = _request("GET", f"/api/v1/admin/{slug}/knowledge", token=agent_token)
    _show(status, body)
    _expect(status, {403}, "agent forbidden")

    _print_step("Owner creates governed enterprise knowledge")
    status, item = _request(
        "POST",
        f"/api/v1/admin/{slug}/knowledge",
        token=owner_token,
        json_body={
            "question": "How is annual leave calculated?",
            "answer": "Demo policy: employees receive 5 annual-leave days after one full year of service.",
            "keywords": "HR,annual leave,policy",
        },
    )
    if status == 201:
        _show(status, item)
    else:
        _show_summary(status, {"created": False, "reason": "embedding_or_service_unavailable"})
    if status == 201:
        print("Knowledge item created.")
    elif status in {400, 500}:
        print("Knowledge creation depends on embedding quota/config; continuing with auth demo.")
    else:
        raise SystemExit(f"create knowledge failed unexpectedly: {status}")

    _print_step("Document import attempt")
    upload_body, headers = _multipart_file(
        "file",
        "demo-policy.txt",
        b"Annual leave policy: employees receive 5 annual-leave days after one full year of service.",
        "text/plain",
    )
    status, body = _request(
        "POST",
        f"/api/v1/admin/{slug}/documents/upload",
        token=owner_token,
        data=upload_body,
        headers=headers,
    )
    _show(status, body)
    if status not in {201, 400, 409, 500}:
        raise SystemExit(f"document upload failed unexpectedly: {status}")
    if status in {400, 500}:
        print("Document import depends on parser/embedding config; continuing.")

    _print_step("Unified enterprise assistant")
    message = os.getenv("SMARTCS_DEMO_CHAT_MESSAGE", "How is annual leave calculated?")
    status, chat = _request(
        "POST",
        f"/api/v1/{slug}/assistant/chat",
        token=employee_token,
        json_body={"session_id": f"demo-session-{int(time.time())}", "message": message},
    )
    _show_summary(
        status,
        {
            "enabled_skills": chat.get("enabled_skills"),
            "has_reply": bool(chat.get("reply")),
            "has_pending_action": bool(chat.get("pending_action")),
        },
    )
    if status not in {200, 503}:
        raise SystemExit(f"assistant chat failed unexpectedly: {status}")
    if status == 503:
        print("Assistant chat needs LLM configuration; role-scoped API wiring is still demonstrated by tests.")

    _print_step("Backend view: knowledge")
    status, body = _request("GET", f"/api/v1/admin/{slug}/knowledge", token=owner_token)
    _show(status, body)
    _expect(status, {200}, "list knowledge")

    _print_step("Backend view: documents")
    status, body = _request("GET", f"/api/v1/admin/{slug}/documents", token=owner_token)
    _show_summary(
        status,
        {
            "total": body.get("total"),
            "items": [
                {
                    "filename": item.get("filename"),
                    "status": item.get("status"),
                    "chunk_count": item.get("chunk_count"),
                }
                for item in body.get("items", [])
            ],
        },
    )
    _expect(status, {200}, "list documents")

    _print_step("Backend view: analytics")
    status, body = _request("GET", f"/api/v1/admin/{slug}/analytics/overview", token=owner_token)
    _show(status, body)
    _expect(status, {200}, "analytics")

    _print_step("Cross-tenant boundary")
    other_slug = f"{slug}-other"
    status, other = _request(
        "POST",
        "/api/v1/auth/register",
        json_body={
            "role": "owner",
            "tenant_slug": other_slug,
            "tenant_name": "Other Tenant",
            "email": f"other-{_suffix()}@example.com",
            "password": password,
            "display_name": "Other Owner",
        },
    )
    _expect(status, {201}, "other tenant register")
    status, body = _request("GET", f"/api/v1/admin/{other_slug}/knowledge", token=owner_token)
    _show(status, body)
    _expect(status, {403}, "cross tenant denied")

    print("\nDemo complete. Open /static/assistant.html for the single-chat UI.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.URLError as exc:
        print(f"Cannot reach SmartCS at {BASE_URL}: {exc}", file=sys.stderr)
        raise SystemExit(1)
