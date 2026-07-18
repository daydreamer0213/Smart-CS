# Citation Rendering and Status Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the HR Agent return canonical authorized source citations even when a configured LLM renders only a document title, then align the project status documents with the delivered HR Agent foundation.

**Architecture:** The agent keeps the current authorization gate: it may answer only after `search_hr_knowledge` returns authorized sources. A small final-answer helper preserves valid model citations, rejects any model-supplied unauthorized citation token, and appends canonical `[source:<id>]` tokens derived only from the authorized source list when the model omitted source tokens entirely. No model retry, new dependency, or retrieval change is added.

**Tech Stack:** Python 3.12, FastAPI, LangChain OpenAI-compatible tool calling, pytest.

## Global Constraints

- Keep the existing source authorization, tenant boundary, and fallback behavior when no authorized source exists.
- Do not expose, log, commit, or print API keys, JWTs, or passwords.
- Keep generated databases, Chroma data, logs, and caches under `D:\DevData`.
- Do not add dependencies or alter the retrieval ranking path.

---

## File Structure

- `app/core/agent/hr_agent.py`: final-answer citation normalization after a successful authorized search.
- `tests/test_hr_agent.py`: regression coverage for a model reply that uses a document filename instead of the canonical citation token.
- `docs/planning/ROADMAP.md`: current delivery status and deferred production-hardening scope.
- `docs/planning/MILESTONE.md`: completed Milestone 1 definition of done and remaining production boundaries.

### Task 1: Normalize Citations From Authorized Retrieval Results

**Files:**
- Modify: `tests/test_hr_agent.py`
- Modify: `app/core/agent/hr_agent.py`

**Interfaces:**
- Consumes: `reply: str` and `sources: list[dict]` returned after `search_hr_knowledge`.
- Produces: the existing `run_hr_agent(...) -> tuple[str, HandoffDraft | None, list[dict]]` reply with only canonical authorized citation tokens.

- [x] **Step 1: Write the failing regression test**

Add parameterized cases to `test_hr_agent_requires_authorized_source_citation` in which the final fake LLM replies are `"年假按制度执行。"` and `"年假按制度执行。[annual-leave-policy.txt]"`; each expected reply includes the original text plus `"[source:policy-1]"`.

- [x] **Step 2: Run the focused test to verify it fails**

Run:

```powershell
& D:\2026.07.09\conda-envs\smart-cs\python.exe -m pytest tests\test_hr_agent.py::test_hr_agent_requires_authorized_source_citation -q
```

Expected: the filename-only case fails because the current agent returns `_UNVERIFIED_REPLY`.

- [x] **Step 3: Add the minimum normalization helper**

In `app/core/agent/hr_agent.py`, add a helper that:

```python
def _render_authorized_citations(reply: str, sources: list[dict]) -> str:
    if _has_authorized_citations(reply, sources):
        return reply
    if re.search(r"\[source:[^\]\s]+\]", reply):
        return _UNVERIFIED_REPLY
    citations = " ".join(f"[source:{source['source_id']}]" for source in sources)
    return f"{reply.rstrip()}\n\n{citations}".strip()
```

Call it only in the final-answer path after `search_attempted` is true and `sources` is nonempty. Keep `_UNVERIFIED_REPLY` for no search, empty search, malformed retrieval, and unavailable retrieval.

- [x] **Step 4: Run the focused test to verify it passes**

Run the command from Step 2.

Expected: all parameterized cases pass; valid citations remain unchanged, citation-free and filename-only replies gain the authorized source ID, and an unauthorized model citation still returns `_UNVERIFIED_REPLY`.

- [x] **Step 5: Commit the tested code change**

```powershell
git add app/core/agent/hr_agent.py tests/test_hr_agent.py
git commit -m "fix: render authorized HR citations"
```

### Task 2: Align Project Status Documents

**Files:**
- Modify: `docs/planning/ROADMAP.md`
- Modify: `docs/planning/MILESTONE.md`

**Interfaces:**
- Consumes: the delivered HR Agent capabilities and explicitly deferred production work.
- Produces: planning documents that do not describe completed JWT, document import, and HR Agent work as pending.

- [x] **Step 1: Replace obsolete Milestone 1 statuses**

Set Milestone 1 to `done`, mark document import, JWT identity boundary, audience-aware RAG, source citation, and confirmed HR handoff lifecycle as delivered. Keep tenant self-service UI out of the completed scope because the backend registration flow is the delivered boundary.

- [x] **Step 2: State only real next-stage production work**

List SSO/SCIM, HRIS or external ticket integration, notification and SLA handling, end-to-end tracing and metrics, CI/CD, and production secret management as pending. Mark WebSocket and Milvus as conditional scale decisions rather than committed scope.

- [x] **Step 3: Verify stale implementation claims are gone**

Run:

```powershell
rg -n "JWT.*(pending|待实现)|Phase 1.2.*(active|pending)|74 项现有测试" docs\planning\ROADMAP.md docs\planning\MILESTONE.md
```

Expected: no matches.

- [ ] **Step 4: Commit documentation alignment**

```powershell
git add docs/planning/ROADMAP.md docs/planning/MILESTONE.md docs/superpowers/plans/2026-07-18-citation-rendering-and-status-docs.md
git commit -m "docs: align HR agent delivery status"
```

### Task 3: Verify The Delivered Demo End To End

**Files:**
- Verify only: `tests/`, `scripts/demo_enterprise_flow.py`, `docs/operations/local-hr-agent-demo.md`

**Interfaces:**
- Consumes: the configured Qwen chat and embedding endpoints plus a new temporary SQLite/Chroma directory.
- Produces: a passing test suite and a live lifecycle demo that exits with code `0`.

- [ ] **Step 1: Run the full regression suite**

```powershell
& D:\2026.07.09\conda-envs\smart-cs\python.exe -m pytest tests -q
```

Expected: all tests pass; the only accepted warning is the known third-party `jieba` / `pkg_resources` deprecation warning.

- [ ] **Step 2: Run an isolated live demo**

Create a timestamped directory under `D:\DevData\smartcs-demo`, run `alembic upgrade head`, start Uvicorn on an unused local port, run `scripts/demo_enterprise_flow.py` with `SMARTCS_BASE_URL` set to that port, and stop the server afterwards.

Expected: the script prints `Live HR Agent demo complete.` and exits `0`; it proves upload, cited answer, pending handoff, confirmation, HR resolution, and cross-tenant `403`.

- [ ] **Step 3: Review and push the branch**

Run `git diff --check origin/main...HEAD`, inspect `git status --short`, commit any verification-only documentation correction if needed, then push `codex/citation-rendering` to `origin`.
