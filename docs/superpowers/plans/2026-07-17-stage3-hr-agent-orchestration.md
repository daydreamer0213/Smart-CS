# Stage 3 HR Agent Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the primary CRM-oriented assistant runtime with a governed HR service Agent that can search authorized policy knowledge, ask for clarification, prepare a confirmation-gated human-support draft, and report the current employee's handoff status.

**Architecture:** Add a focused `hr_agent` module beside the retained Sales Copilot `business_agent`. The HR Agent reuses the existing tenant-aware retrieval tool and HR support service, exposes only typed HR Skills to the model, and returns a typed handoff draft through the authenticated assistant API. Deterministic backend controls continue to own tenant isolation, source visibility, draft persistence, confirmation, and lifecycle writes.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, Pydantic v2, LangChain tool calling, pytest

## Global Constraints

- Keep `app/core/agent/business_agent.py` and `/business/chat` isolated as the deprecated Sales Copilot Lab.
- Add no dependency, migration, framework, UI, HRIS integration, or autonomous HR decision.
- The HR Agent may create only a pending `HandoffDraft`; only the existing confirmation endpoint may create `SupportHandoff`.
- Every knowledge answer must be based on an authorized tool result and retain source identifiers in the tool observation.
- Every database query remains scoped by `tenant_id` and the authenticated employee where applicable.
- Do not log raw employee questions, retrieved passages, or handoff payloads.

---

### Task 1: HR Skill Catalog and Agent Loop

**Files:**
- Create: `app/core/agent/hr_agent.py`
- Create: `tests/test_hr_agent.py`

**Interfaces:**
- Consumes: `app.core.agent.tools.search_knowledge`, `hr_support_service.create_handoff_draft(...)`, and `hr_support_service.list_my_handoffs(...)`.
- Produces: `allowed_hr_skill_names() -> list[str]` and `run_hr_agent(db, tenant_id, tenant_slug, user, message, history=None) -> tuple[str, HandoffDraft | None, list[dict]]`.

- [ ] **Step 1: Write failing tool-catalog and behavior tests**

```python
def test_hr_agent_exposes_only_hr_skills():
    assert allowed_hr_skill_names() == [
        "hr.knowledge.search",
        "hr.clarify",
        "hr.support.draft",
        "hr.support.status",
    ]

async def test_hr_agent_can_prepare_handoff_draft(db, test_tenant, monkeypatch):
    employee = make_employee(db, test_tenant)
    monkeypatch.setattr("app.core.agent.hr_agent.ChatOpenAI", FakeDraftLLM)
    reply, draft, sources = await run_hr_agent(
        db, test_tenant.id, test_tenant.slug, employee,
        "跨境工作期间年假怎么处理？",
    )
    assert draft.question == "跨境工作期间年假怎么处理？"
    assert draft.status == "pending"
    assert sources == []
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_hr_agent.py -q`

Expected: collection fails because `app.core.agent.hr_agent` does not exist.

- [ ] **Step 3: Implement the minimum governed HR Agent**

```python
HR_SKILL_NAMES = [
    "hr.knowledge.search",
    "hr.clarify",
    "hr.support.draft",
    "hr.support.status",
]

async def run_hr_agent(db, tenant_id, tenant_slug, user, message, history=None):
    set_hr_runtime(db, tenant_id, tenant_slug, user, message)
    tools = [search_hr_knowledge, ask_clarifying_question,
             draft_handoff, get_handoff_status]
    # Reuse the existing bounded three-round tool loop and return
    # (reply, pending_handoff, authorized_sources).
```

The system prompt must require knowledge search before a policy conclusion, prohibit unsupported conclusions, permit clarification for vague requests, and require `draft_handoff` for exceptions, no-source cases, or explicit human-help requests.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest tests/test_hr_agent.py -q`

Expected: all Stage 3 agent tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/core/agent/hr_agent.py tests/test_hr_agent.py
git commit -m "feat: add governed HR service agent"
```

### Task 2: Primary Assistant HR Contract

**Files:**
- Modify: `app/api/assistant.py`
- Modify: `app/schemas/assistant.py`
- Modify: `tests/test_assistant_api.py`
- Modify: `tests/test_primary_boundary.py`

**Interfaces:**
- Consumes: `run_hr_agent(...)` and `allowed_hr_skill_names()` from Task 1.
- Produces: `AssistantChatResponse.sources: list[SourceCitation]` and `AssistantChatResponse.pending_handoff: HandoffDraftResponse | None`.

- [ ] **Step 1: Write failing API contract tests**

```python
async def test_assistant_returns_hr_skills_and_pending_handoff(
    client, db, test_tenant, monkeypatch,
):
    employee = make_employee(db, test_tenant)
    draft = create_handoff_draft(
        db, test_tenant.id, employee.id, "请转 HR 人工", "员工明确要求人工", [],
    )

    async def fake_hr_agent(*_args, **_kwargs):
        return "已准备待确认的 HR 支持请求。", draft, []

    monkeypatch.setattr("app.api.assistant.run_hr_agent", fake_hr_agent)
    employee_headers = {"Authorization": f"Bearer {create_access_token(employee)}"}
    response = await client.post(
        f"/api/v1/{test_tenant.slug}/assistant/chat",
        headers=employee_headers,
        json={"message": "请转 HR 人工"},
    )
    body = response.json()
    assert body["enabled_skills"] == [
        "hr.knowledge.search", "hr.clarify",
        "hr.support.draft", "hr.support.status",
    ]
    assert body["pending_handoff"]["status"] == "pending"
    assert body["sources"] == []
    assert "pending_action" not in body

async def test_primary_assistant_does_not_expose_crm_confirmation(
    client, db, test_tenant,
):
    employee = make_employee(db, test_tenant)
    employee_headers = {"Authorization": f"Bearer {create_access_token(employee)}"}
    response = await client.post(
        f"/api/v1/{test_tenant.slug}/assistant/action-drafts/not-an-hr-draft/confirm",
        headers={**employee_headers, "Idempotency-Key": "legacy-crm-0001"},
    )
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_assistant_api.py tests/test_primary_boundary.py -q`

Expected: failures show the assistant still calls `run_business_agent` and returns `pending_action`.

- [ ] **Step 3: Switch only the primary assistant surface**

```python
class AssistantChatResponse(BaseModel):
    session_id: str
    reply: str
    enabled_skills: list[str]
    sources: list[SourceCitation] = Field(default_factory=list)
    pending_handoff: HandoffDraftResponse | None = None
```

`assistant.py` must call `run_hr_agent`, serialize the draft with `sources=draft.sources_json or []`, persist only the completed user/reply turn, and remove its duplicate CRM action-confirmation route. The deprecated `/business/chat` and `/business/action-drafts/{draft_id}/confirm` routes remain untouched inside the Sales Copilot Lab.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest tests/test_assistant_api.py tests/test_primary_boundary.py tests/test_business_api.py -q`

Expected: primary assistant HR tests and isolated Sales Copilot regression tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/api/assistant.py app/schemas/assistant.py tests/test_assistant_api.py tests/test_primary_boundary.py
git commit -m "feat: make HR agent the primary assistant"
```

### Task 3: Safety and Conversation Regression

**Files:**
- Modify: `tests/test_hr_agent.py`
- Modify: `tests/test_security.py`

**Interfaces:**
- Consumes: Stage 1 tenant-scoped models, Stage 2 handoff APIs, and Tasks 1-2 Agent/API behavior.
- Produces: regression evidence for evidence-bound answers, clarification, confirmation gating, tenant isolation, and payload-safe logs.

- [ ] **Step 1: Add failing safety tests**

```python
async def test_no_source_can_prepare_draft_but_not_handoff(db, test_tenant, monkeypatch):
    employee = make_employee(db, test_tenant)
    monkeypatch.setattr("app.core.agent.hr_agent.ChatOpenAI", FakeNoSourceDraftLLM)
    reply, draft, sources = await run_hr_agent(
        db, test_tenant.id, test_tenant.slug, employee,
        "跨境工作期间年假怎么处理？",
    )
    assert draft is not None
    assert sources == []
    assert db.query(SupportHandoff).filter(
        SupportHandoff.tenant_id == test_tenant.id,
        SupportHandoff.requester_user_id == employee.id,
    ).count() == 0

async def test_vague_request_can_ask_clarification_without_write(db, test_tenant, monkeypatch):
    employee = make_employee(db, test_tenant)
    monkeypatch.setattr("app.core.agent.hr_agent.ChatOpenAI", FakeClarifyingLLM)
    reply, draft, sources = await run_hr_agent(
        db, test_tenant.id, test_tenant.slug, employee,
        "我的假期怎么办？",
    )
    assert "请说明" in reply
    assert draft is None
    assert sources == []
```

Also assert lifecycle logs contain identifiers and counts but neither the raw question nor source excerpts.

- [ ] **Step 2: Run tests and verify RED or missing coverage**

Run: `python -m pytest tests/test_hr_agent.py tests/test_security.py -q`

Expected: new assertions fail until the Agent observations and logging fields match the governed contract.

- [ ] **Step 3: Apply the minimum production corrections**

Keep policy enforcement in tool implementations and services. Do not add a general policy engine or persisted LangGraph checkpoint.

- [ ] **Step 4: Run focused and full verification**

Run: `python -m pytest tests/test_hr_agent.py tests/test_assistant_api.py tests/test_hr_support_api.py tests/test_security.py -q`

Expected: focused suite passes.

Run: `python -m pytest tests -q`

Expected: full suite passes with no new warning category.

- [ ] **Step 5: Commit**

```bash
git add app tests
git commit -m "test: cover governed HR agent decisions"
```

### Task 4: Independent Review and Stage Report

**Files:**
- No production files unless review identifies a reproduced defect.

- [ ] **Step 1: Review the diff against the approved design**

Run: `git diff --check 7499d14..HEAD`

Confirm that the primary assistant has no CRM imports, HR tools cannot persist `SupportHandoff`, tenant/user scopes are server-derived, and logs exclude question/source payloads.

- [ ] **Step 2: Run final verification from a clean process**

Run: `python -m pytest tests -q`

Expected: all tests pass.

- [ ] **Step 3: Report and stop**

Report changed behavior, exact verification output, commit identifiers, resume bullet, interview explanation, API demo path, and limitations. Stop for user acceptance before Stage 4.
