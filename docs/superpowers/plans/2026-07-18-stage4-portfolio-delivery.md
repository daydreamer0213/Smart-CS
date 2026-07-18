# Stage 4 Portfolio Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deliver a reproducible, honest HR service Agent demo and a consistent job-search narrative for SmartCS without adding product capabilities.

**Architecture:** Keep the existing FastAPI, Alembic, JWT, RAG, HR Agent, and handoff APIs unchanged. Replace the stale CRM-oriented live script with a standard-library HTTP client that exercises the existing HR service lifecycle against a locally running API, then align the README, runbook, and interview documents to that exact contract.

**Tech Stack:** Python 3.12 from D:\2026.07.09\conda-envs\smart-cs\python.exe, FastAPI, SQLAlchemy, Alembic, pytest, urllib.request, PowerShell.

## Global Constraints

- The primary product is a multi-tenant internal-employee HR service Agent. /business/* is an isolated Sales Copilot Lab and must not be presented as the primary workflow.
- The demo uses only fictional Beichen tenant, employee, policy, and HR request data. It must never print access tokens, API keys, passwords, or .env values.
- A live demo passes only when document import, model-backed answer with source citations, draft confirmation, HR status update, employee status lookup, and tenant denial all succeed. A 503 is a failure, not a pass.
- Reuse existing HTTP APIs and the Python standard library. Add no framework, dependency, frontend, FastGPT runtime, provider abstraction, or runtime product capability.
- Keep fresh demo database, Chroma, and logs under D:\DevData\smartcs-demo. Do not write generated data to C:.
- Use online alembic upgrade head for fresh databases. Do not document offline --sql as a greenfield initialization path.
- Do not change production Agent, RAG, auth, migration, or HR-service behavior in this stage.
- State honest boundaries: this is not deployed production SaaS, SSO/HRIS, approval, notification, SLA, or full observability.

---

## File Structure

- Modify: scripts/demo_enterprise_flow.py - strict, redacted live HR lifecycle demo.
- Create: tests/test_demo_enterprise_flow.py - deterministic script contract tests.
- Modify: README.md - canonical HR Agent position and delivery commands.
- Create: docs/operations/local-hr-agent-demo.md - two-terminal operator runbook.
- Modify: docs/interview/SMARTCS_DEMO_SCRIPT.md - three-minute Chinese presentation.
- Modify: docs/interview/SMARTCS_INTERVIEW.md - resume/interview content.
- Modify: docs/interview/SMARTCS_DELIVERY_PACKAGE.md - delivery summary consistent with the above.

### Task 1: Replace the stale CRM demo with a strict HR lifecycle demo

**Files:**
- Create: tests/test_demo_enterprise_flow.py
- Modify: scripts/demo_enterprise_flow.py

**Interfaces:**
- Consumes: POST /api/v1/auth/register, POST /api/v1/admin/{tenant_slug}/documents/upload, POST /api/v1/{tenant_slug}/assistant/chat, POST /api/v1/{tenant_slug}/hr-support/drafts/{draft_id}/confirm, GET/PATCH /api/v1/{tenant_slug}/hr-support/*.
- Produces: main() -> int, multipart support for repeated audience_roles form fields, and a non-zero process exit when any required live step fails.

- [ ] **Step 1: Write failing tests**

Create tests/test_demo_enterprise_flow.py:

~~~
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
~~~

- [ ] **Step 2: Run the new test to verify it fails**

Run:

~~~powershell
& D:\2026.07.09\conda-envs\smart-cs\python.exe -m pytest tests/test_demo_enterprise_flow.py -q
~~~

Expected: FAIL because the old multipart helper has no fields argument and the old script has neither DemoFailure nor this HR sequence.

- [ ] **Step 3: Implement the minimum script behavior**

In scripts/demo_enterprise_flow.py, retain BASE_URL and _request. Add exactly these helpers:

~~~python
class DemoFailure(RuntimeError):
    pass


def _require(status: int, expected: set[int], label: str) -> None:
    if status not in expected:
        raise DemoFailure(f"{label} failed: expected {sorted(expected)}, got {status}")


def _require_live_chat(status: int, body: dict, label: str) -> None:
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
~~~

Replace the helper with a repeated-form-field encoder:

~~~python
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
~~~

Replace the old agent/CRM/analytics flow with this exact HTTP sequence, applying _require to every expected response:

1. GET /health returns 200.
2. Register owner for slug beichen-hr-{suffix}.
3. Owner registers one admin and one employee.
4. Owner uploads beichen-annual-leave-policy.txt with fields=[("audience_roles", "employee")]; require 201 and status ready.
5. Employee asks 北辰科技年假如何计算？ through /assistant/chat; require 200 and _require_cited_answer.
6. Employee asks 我在海外派驻期间需要申请年假例外，请转 HR 人工处理。; require 200 and _require_pending_draft.
7. Employee confirms the returned draft at /hr-support/drafts/{draft_id}/confirm with Idempotency-Key demo-confirm-{suffix}; require 200/open.
8. HR admin GETs /hr-support/admin; require the official handoff ID.
9. HR admin PATCHes /hr-support/admin/{handoff_id} with status assigned and assigned_user_id from the admin response user.id; require assigned.
10. HR admin PATCHes the same route with status resolved and resolution_note 已由 HR 核验：海外派驻例外需人工审核。; require resolved.
11. Employee GETs /hr-support/me; require its official handoff ID is resolved.
12. Create another owner tenant and call its /hr-support/me with the first tenant employee JWT; require 403.

Print only tenant slug, document ID, source IDs, draft/handoff IDs, and statuses. Remove old acceptance of document import 400/500 and assistant 503, CRM knowledge creation, agent-forbidden/analytics steps, pending_action, and static UI completion text. Keep this entry point:

~~~python
if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DemoFailure as exc:
        print(f"Live HR Agent demo failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except urllib.error.URLError as exc:
        print(f"Cannot reach SmartCS at {BASE_URL}: {exc}", file=sys.stderr)
        raise SystemExit(1)
~~~

- [ ] **Step 4: Run tests to verify they pass**

~~~powershell
& D:\2026.07.09\conda-envs\smart-cs\python.exe -m pytest tests/test_demo_enterprise_flow.py -q
& D:\2026.07.09\conda-envs\smart-cs\python.exe -m pytest tests/test_assistant_api.py tests/test_hr_support_api.py tests/test_admin_document_api.py -q
~~~

Expected: 3 new tests pass, followed by all affected API tests passing.

- [ ] **Step 5: Commit**

~~~powershell
git add scripts/demo_enterprise_flow.py tests/test_demo_enterprise_flow.py
git commit -m "feat: add live HR agent demo"
~~~

### Task 2: Make project and interview documentation say the same thing

**Files:**
- Modify: README.md
- Create: docs/operations/local-hr-agent-demo.md
- Modify: docs/interview/SMARTCS_DEMO_SCRIPT.md
- Modify: docs/interview/SMARTCS_INTERVIEW.md
- Modify: docs/interview/SMARTCS_DELIVERY_PACKAGE.md

**Interfaces:**
- Consumes: Task 1 script status/ID/citation output and failure behavior.
- Produces: one canonical operator path and an HR service Agent interview narrative.

- [ ] **Step 1: Create the operator runbook**

Create docs/operations/local-hr-agent-demo.md with these exact sections: goal, prerequisites, terminal one, terminal two, observable success criteria, and troubleshooting.

It must include:

~~~powershell
cd D:\2026.07.09\AAA\smart-cs
$demoRoot = "D:/DevData/smartcs-demo/" + (Get-Date -Format "yyyyMMdd-HHmmss")
New-Item -ItemType Directory -Force -Path $demoRoot | Out-Null
$env:DATABASE_URL = "sqlite:///$demoRoot/smartcs-demo.db"
$env:CHROMA_PERSIST_DIR = "$demoRoot/chroma"
$env:LOG_DIR = "$demoRoot/logs"
& D:\2026.07.09\conda-envs\smart-cs\python.exe -m alembic upgrade head
& D:\2026.07.09\conda-envs\smart-cs\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
~~~

~~~powershell
cd D:\2026.07.09\AAA\smart-cs
$env:SMARTCS_BASE_URL = "http://127.0.0.1:8000"
& D:\2026.07.09\conda-envs\smart-cs\python.exe scripts\demo_enterprise_flow.py
~~~

State that .env supplies LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, EMBEDDING_API_KEY, EMBEDDING_BASE_URL, and EMBEDDING_MODEL without printing them. Explain that alembic upgrade head is the supported fresh-db path and 503 is a model/provider/network/quota failure, not success. Troubleshooting rows must cover Cannot reach SmartCS, 503, document import failure, citation missing, and migration failure; every row says not to paste secrets into tickets or screenshots.

- [ ] **Step 2: Rewrite README.md**

Use this opening and workflow wording:

~~~markdown
# SmartCS

SmartCS 是一个面向企业内部员工的多租户 HR 服务 Agent 后端工程样板。它的主线不是“聊天”，而是把制度知识问答、来源引用、例外转人工、员工确认、HR 处理和租户边界放进同一条可测试服务链路。

## 核心闭环

1. 员工通过 JWT 进入所属租户。
2. HR Agent 从本人可访问的制度文档中检索，并在回答中提供 [source:<id>] 引用。
3. 制度没有覆盖、信息不足或员工明确要求人工处理时，Agent 只创建待确认草稿。
4. 员工显式确认后，后端以幂等键创建正式 HR 支持请求并记录最小审计状态。
5. owner/admin 指派或解决请求；员工只能查看自己的状态。
6. 文档、检索、工单和 API 都按租户与角色做后端边界校验。
~~~

Include current FastAPI/SQLAlchemy/Alembic/ChromaDB/BM25/LangGraph/JWT stack, a Mermaid diagram ending in HR Support Handoff, role table, test command, link to the new runbook, and links to the three interview documents. Remove the nonexistent SMARTCS_FINAL_PITCH.md link. State only once that /business/* is a JWT-protected Sales Copilot Lab kept for historical regression coverage, not the primary route or interview demo. Do not claim hash embedding is a live-answer demo mode and do not call 503 successful.

- [ ] **Step 3: Rewrite interview artefacts**

In SMARTCS_DEMO_SCRIPT.md, write a Chinese three-minute narration aligned exactly to Task 1: 200 health, tenant/user identity, employee audience document, cited answer, pending draft, confirmed open handoff, HR assigned then resolved, employee status, and cross-tenant 403.

In SMARTCS_INTERVIEW.md, insert these resume bullets:

~~~markdown
- 独立构建 FastAPI 多租户 HR 服务 Agent 后端，覆盖 JWT 身份边界、角色化文档权限、文档导入、BM25 + 向量检索与带来源引用的制度问答。
- 设计“检索不足或例外 -> 转人工草稿 -> 员工确认 -> 幂等建单 -> HR 指派/解决 -> 员工可见状态”的受控服务闭环，并以最小审计快照记录状态变化。
- 使用 pytest 覆盖认证、租户隔离、文档受众、检索失败降级、Agent 工具调用和转人工生命周期，并提供可复现的本地实时演示脚本。
~~~

Also add a 30-second pitch, two-minute explanation, deep-dive answers for Agent/citations/confirmation/tenant boundary/retrieval failure/why not HRIS, and realistic next steps: SSO/SCIM, HRIS or ticket adapter, notification/SLA, tracing/metrics, CI/CD, and production secrets.

In SMARTCS_DELIVERY_PACKAGE.md, align one-line position, bullets, demo route, boundaries, and links to the same HR terms. Remove claims that CRM is primary.

- [ ] **Step 4: Run mechanical consistency checks**

~~~powershell
rg -n "pending_action|controlled CRM operations|role-scoped CRM Skills|CRM Skills|SMARTCS_FINAL_PITCH" README.md docs/interview scripts/demo_enterprise_flow.py
rg -n "HR 服务 Agent|转人工|pending_handoff|跨租户" README.md docs/operations docs/interview scripts/demo_enterprise_flow.py
git diff --check
~~~

Expected: first command exits 1; second finds HR workflow in every delivery artefact; diff check has no whitespace errors. The one isolated Sales Copilot Lab note is allowed.

- [ ] **Step 5: Commit**

~~~powershell
git add README.md docs/operations/local-hr-agent-demo.md docs/interview/SMARTCS_DEMO_SCRIPT.md docs/interview/SMARTCS_INTERVIEW.md docs/interview/SMARTCS_DELIVERY_PACKAGE.md
git commit -m "docs: polish HR agent portfolio delivery"
~~~

### Task 3: Verify deterministic evidence and live delivery contract

**Files:** verify all Task 1 and Task 2 files only.

**Interfaces:**
- Consumes: the script and runbook.
- Produces: deterministic test evidence, fresh online migration evidence, and either a successful live demo or a precise non-secret configuration block.

- [ ] **Step 1: Run full deterministic tests**

~~~powershell
& D:\2026.07.09\conda-envs\smart-cs\python.exe -m pytest tests -q
~~~

Expected: all tests pass. Record exact count and any pre-existing warning; this is not a live-model quality test.

- [ ] **Step 2: Run fresh online migration smoke test on D:**

~~~powershell
$migrationRoot = "D:/DevData/smartcs-demo/migration-" + (Get-Date -Format "yyyyMMdd-HHmmss")
New-Item -ItemType Directory -Force -Path $migrationRoot | Out-Null
$env:DATABASE_URL = "sqlite:///$migrationRoot/smartcs-migration.db"
& D:\2026.07.09\conda-envs\smart-cs\python.exe -m alembic upgrade head
~~~

Expected: Alembic reaches head and the SQLite database exists under D:\DevData\smartcs-demo.

- [ ] **Step 3: Execute live demo using the two-terminal runbook**

Do not show .env, tokens, passwords, or response bodies containing sensitive fields. Capture only:

~~~text
health: 200
document upload: 201, status=ready
policy answer: 200, source_ids=[...]
handoff draft: pending
confirmed handoff: open
HR lifecycle: assigned -> resolved
employee status: resolved
cross-tenant boundary: 403
~~~

If the script reports model configuration, provider, network, embedding, or quota failure, retain the non-zero exit and report the live demo as blocked. Do not change code to turn this into success.

- [ ] **Step 4: Final repository checks**

~~~powershell
git status --short
git log --oneline -3
git diff HEAD~2..HEAD --check
~~~

Expected: clean worktree after the two Stage 4 commits, both commits visible, no whitespace errors.

---

## Self-Review

- **Spec coverage:** Task 1 makes the fictional live demo strict. Task 2 makes README, runbook, and interview content HR-first and consistent. Task 3 verifies tests, D: migration, live lifecycle output, and failure honesty.
- **YAGNI check:** No product behavior, provider integration, workflow framework, frontend, or infrastructure is added. Existing urllib and API endpoints are reused.
- **Placeholder scan:** Test names, API paths, expected statuses, file paths, commands, and commit messages are specified.
- **Interface consistency:** The plan uses pending_handoff, drafts/{draft_id}/confirm, hr-support/admin/{handoff_id}, and hr-support/me, matching the current FastAPI contracts.
