# Stage 3 Document Role ACL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining Stage 3 authorization gap so uploaded HR documents are visible only to authenticated tenant roles explicitly listed by administrators, while existing documents remain visible to all roles in their tenant.

**Architecture:** Store `audience_roles` as JSON on `Document`, matching the existing `KnowledgeItem` contract: an empty list means every role in the tenant. Accept the role list as a repeated multipart form field during upload, return it from admin document APIs, and enforce it in the shared retrieval tool before document chunks become Agent sources. Replace model-controlled unknown tool names in structured logs with a fixed safe classification.

**Tech Stack:** Python 3.11, FastAPI multipart forms, SQLAlchemy JSON, Alembic, Pydantic v2, pytest

## Global Constraints

- This user-approved addendum supersedes Stage 3's "no migration" constraint only for one `documents.audience_roles` migration.
- Allowed roles are exactly `owner`, `admin`, `agent`, and `employee`.
- `audience_roles=[]` means all authenticated roles in the same tenant, preserving existing document behavior.
- Keep tenant filtering and role filtering in the backend; never trust a tenant or role supplied by the model.
- Add no dependency, UI, HRIS integration, generic ACL framework, or role hierarchy.
- Do not log raw model-provided tool names, employee questions, retrieved passages, or handoff payloads.

---

### Task 1: Persist and Expose Document Audience Roles

**Files:**
- Create: `migrations/versions/e4f5a6b7c8d9_add_document_audience_roles.py`
- Modify: `app/models/document.py`
- Modify: `app/schemas/document.py`
- Modify: `app/services/document_service.py`
- Modify: `app/api/admin/document.py`
- Modify: `tests/test_document_service.py`
- Modify: `tests/test_admin_document_api.py`

**Interfaces:**
- Produces: `Document.audience_roles: list[str]`, defaulting to `[]`.
- Produces: `upload_document(..., audience_roles: list[str] | None = None) -> Document`.
- Produces: multipart upload field `audience_roles` as a repeated list of the four allowed role literals.
- Produces: `audience_roles` in both `DocumentUploadResponse` and `DocumentResponse`.

- [ ] **Step 1: Add failing persistence and API contract tests**

```python
async def test_upload_document_persists_audience_roles(db, test_tenant, monkeypatch):
    monkeypatch.setattr("app.services.document_service.parse_file", lambda *_: "policy text")
    monkeypatch.setattr("app.services.document_service.chunk_text", fake_chunk_text)
    install_fake_retrieval(monkeypatch)
    doc = await upload_document(
        db, test_tenant.id, test_tenant.slug, "policy.txt", b"policy text",
        audience_roles=["admin"],
    )
    assert doc.audience_roles == ["admin"]

async def test_document_upload_accepts_and_returns_audience_roles(
    admin_client, test_tenant, monkeypatch,
):
    captured = {}
    async def fake_upload(*_args, audience_roles=None, **_kwargs):
        captured["audience_roles"] = audience_roles
        return SimpleNamespace(
            id="doc-1", filename="policy.txt", chunk_count=1,
            status="ready", audience_roles=audience_roles,
        )
    monkeypatch.setattr(document_service, "upload_document", fake_upload)
    response = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/documents/upload",
        files={"file": ("policy.txt", b"policy", "text/plain")},
        data={"audience_roles": "admin"},
    )
    assert response.status_code == 201
    assert captured["audience_roles"] == ["admin"]
    assert response.json()["audience_roles"] == ["admin"]
```

- [ ] **Step 2: Run the new tests and verify RED**

Run: `python -m pytest tests/test_document_service.py tests/test_admin_document_api.py -q`

Expected: the new tests fail because the model, service signature, form input, and responses do not yet contain `audience_roles`.

- [ ] **Step 3: Add the minimal model, migration, service, and API changes**

```python
# app/models/document.py
audience_roles = Column(JSON, default=list, nullable=False)

# app/services/document_service.py
async def upload_document(..., audience_roles: list[str] | None = None) -> Document:
    doc = Document(..., audience_roles=audience_roles or [])

# app/api/admin/document.py
audience_roles: list[AudienceRole] = Form(default=[])
doc = await document_service.upload_document(
    db, tenant.id, tenant_slug, file.filename, data,
    audience_roles=audience_roles,
)
```

The Alembic upgrade adds non-null JSON `audience_roles` with server default `'[]'`; downgrade removes only that column. The revision must set `down_revision = "d1e2f3a4b5c6"`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python -m pytest tests/test_document_service.py tests/test_admin_document_api.py -q`

Expected: all focused tests pass, including omitted-role backward compatibility.

- [ ] **Step 5: Commit exact files**

```bash
git add migrations/versions/e4f5a6b7c8d9_add_document_audience_roles.py app/models/document.py app/schemas/document.py app/services/document_service.py app/api/admin/document.py tests/test_document_service.py tests/test_admin_document_api.py
git commit -m "feat: add document audience roles"
```

### Task 2: Enforce Roles in Retrieval and Sanitize Unknown Tool Logs

**Files:**
- Modify: `app/core/agent/tools.py`
- Modify: `app/core/agent/hr_agent.py`
- Modify: `tests/test_security.py`
- Modify: `tests/test_hr_agent.py`

**Interfaces:**
- Consumes: `Document.audience_roles` from Task 1 and the authenticated role stored by `set_runtime`.
- Produces: document chunks only when `document.audience_roles` is empty or contains the authenticated role.
- Produces: `tool_name="unknown_tool"` and `result_code="NOT_ALLOWED"` for any unrecognized model tool call.

- [ ] **Step 1: Add failing employee/admin/backward-compatibility tests**

```python
restricted_document = Document(
    tenant_id=test_tenant.id, filename="admin-policy.txt", file_type="txt",
    file_hash="admin-policy-hash", status="ready", audience_roles=["admin"],
)
legacy_document = Document(
    tenant_id=test_tenant.id, filename="general-policy.txt", file_type="txt",
    file_hash="general-policy-hash", status="ready", audience_roles=[],
)

set_hr_runtime(db, test_tenant.id, test_tenant.slug, employee, "policy")
employee_result = json.loads(await search_hr_knowledge.ainvoke({"query": "policy"}))
assert restricted_chunk.id not in {item["source_id"] for item in employee_result["sources"]}
assert legacy_chunk.id in {item["source_id"] for item in employee_result["sources"]}

set_hr_runtime(db, test_tenant.id, test_tenant.slug, admin, "policy")
admin_result = json.loads(await search_hr_knowledge.ainvoke({"query": "policy"}))
assert restricted_chunk.id in {item["source_id"] for item in admin_result["sources"]}
```

Add an HR Agent test whose fake LLM requests a malicious unknown tool name and assert the captured structured log contains fixed `tool_name="unknown_tool"` while the malicious name is absent from all event fields.

- [ ] **Step 2: Run the new tests and verify RED**

Run: `python -m pytest tests/test_security.py tests/test_hr_agent.py -q`

Expected: the employee sees the admin-only document and the malicious unknown tool name appears in structured logs.

- [ ] **Step 3: Apply the two minimum guards**

```python
# app/core/agent/tools.py, before appending a document chunk
if document.audience_roles and role not in document.audience_roles:
    continue

# app/core/agent/hr_agent.py, unknown tool path
_log_tool(ctx, "unknown_tool", "NOT_ALLOWED", 0, time.monotonic())
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python -m pytest tests/test_security.py tests/test_hr_agent.py -q`

Expected: restricted employee access is denied, admin access and empty-list compatibility pass, and logs contain no model-controlled tool name.

- [ ] **Step 5: Commit exact files**

```bash
git add app/core/agent/tools.py app/core/agent/hr_agent.py tests/test_security.py tests/test_hr_agent.py
git commit -m "fix: enforce document role boundaries"
```

### Task 3: Migration Smoke Test and Stage 3 Acceptance

**Files:**
- No production files unless a reproduced defect requires a test-first correction.

- [ ] **Step 1: Verify the migration on a disposable database under `D:\DevData`**

Run:

```powershell
python -c "from alembic.config import Config; from alembic import command; c=Config('alembic.ini'); c.set_main_option('sqlalchemy.url', 'sqlite:///D:/DevData/smartcs-acl-migration-smoke.db'); command.upgrade(c, 'head')"
```

Expected: Alembic applies through revision `e4f5a6b7c8d9`, and the `documents.audience_roles` column is non-null with existing rows represented as `[]`.

- [ ] **Step 2: Run diff and full-suite checks from a clean process**

Run: `git diff --check 311b6ef..HEAD`

Expected: no whitespace errors.

Run: `python -m pytest tests -q`

Expected: the complete suite passes with no new warning category.

- [ ] **Step 3: Request independent correctness and scope review**

Review the full `311b6ef..HEAD` diff for tenant/role authorization, migration compatibility, upload validation, log payload safety, regression risk, and unnecessary complexity.

- [ ] **Step 4: Remove only untracked review scratch data and report**

After confirming the resolved path is `D:\DevData\smart-cs-hr-agent-foundation\.superpowers`, remove that untracked directory. Report behavior, exact test output, commits, resume bullet, interview explanation, API demo path, limitations, and stop before Stage 4.
