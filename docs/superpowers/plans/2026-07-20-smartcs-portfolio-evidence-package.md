# SmartCS Portfolio Evidence Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a traceable, redacted SmartCS evidence package that can be reviewed independently and later handed to the portfolio frontend.

**Architecture:** Run the existing SmartCS application against a fresh D-drive database and fictional HR data, preserve sanitized raw outputs, then render a dependency-free static evidence page from an explicit manifest. Screenshots and video are exports of that page and the same live run; no new SmartCS product feature or second frontend is introduced.

**Tech Stack:** Python 3.11, FastAPI, Alembic, pytest, PowerShell, static HTML/CSS, Playwright/browser capture, FFmpeg only if already available.

## Global Constraints

- Store generated evidence, databases, logs, screenshots, and video under `D:\DevData\smartcs\portfolio-evidence`; do not place large generated assets on `C:`.
- Use only fictional Beichen Technology data and `example.com` or `example.test` identities.
- Never record or export API keys, JWTs, passwords, cookies, authorization headers, `.env` contents, `storage_key`, physical document paths, or unrelated desktop windows.
- Every visible status and metric must come from a real run at one recorded Git commit.
- A live policy answer without both structured sources and a `[source:<id>]` token invalidates SC-02 for that run.
- Keep the recorded M2-5 limitations visible: curated corpus, HashEmbedding is non-semantic, BM25 contribution 11, vector contribution 0, and `payroll-contact` is the retained failure.
- Do not add an HRIS integration, Agent tool, SmartCS frontend, portfolio frontend dependency, or visual framework.
- Preserve existing user changes in the main worktree; implementation runs in `codex/portfolio-evidence-package`.

---

### Task 1: E1 Reproduce And Collect Raw Evidence

**Files:**
- Modify: `scripts/demo_enterprise_flow.py`
- Test: `tests/test_demo_enterprise_flow.py`
- Read: `scripts/demo_enterprise_flow.py`
- Read: `scripts/evaluate_rag_retrieval.py`
- Read: `docs/operations/local-hr-agent-demo.md`
- Create outside Git: `D:\DevData\smartcs\portfolio-evidence\raw\<run-id>\*`
- Create outside Git: `D:\DevData\smartcs\portfolio-evidence\manifest.json`

**Interfaces:**
- Consumes: the committed SmartCS API, fictional fixtures, configured chat and embedding providers.
- Produces: sanitized demo output, RAG report, pytest output, run metadata, and source paths used by later tasks.

- [ ] **Step 1: Verify configuration without printing secret values**

Check only whether required values are non-empty and record the non-secret model identifiers. Stop if the model or embedding configuration is incomplete.

- [ ] **Step 2: Create a fresh evidence run directory on D:**

Create `raw\<UTC timestamp>-<commit7>` with subdirectories for the database, Chroma data, logs, and command output.

- [ ] **Step 3: Initialize a fresh database**

Run:

```powershell
python -m alembic upgrade head
```

Expected: exit code 0 against the evidence run database.

- [ ] **Step 4: Start SmartCS and verify health**

Run Uvicorn on an unused localhost port with all generated paths redirected to the evidence run directory. Verify `/health` returns HTTP 200.

- [ ] **Step 5: Run the existing enterprise demo**

Before the evidence run, add one TDD-protected safe summary for the cited answer. The summary may include only `reply` and the source fields `source_type`, `source_id`, `title`, `page_start`, `page_end`, `section_path`, and `element_types`; it must exclude `excerpt`, credentials, storage keys, and physical paths. Run `python -m pytest tests/test_demo_enterprise_flow.py -q` red then green.

Run:

```powershell
python scripts\demo_enterprise_flow.py
```

Expected: exit code 0, a cited policy answer, governed document states, confirmed HR handoff lifecycle, and cross-tenant denial. Save stdout and stderr separately, then scan both for forbidden secret patterns.

- [ ] **Step 6: Run the deterministic retrieval evaluation**

Run `scripts\evaluate_rag_retrieval.py` with its fixed fixtures and write the JSON report into the run directory. Verify the report schema, metric counts, contribution counts, and retained failure query instead of copying old documentation values.

- [ ] **Step 7: Run the fresh full regression suite**

Run:

```powershell
python -m pytest -q
```

Expected: exit code 0. Preserve the exact summary and warnings in the raw run directory.

- [ ] **Step 8: Write and validate the manifest**

Record run ID, Git commit, capture time, commands, relative raw source paths, extracted conclusions, required limitations, and SHA-256 hashes. Reject absolute user-profile paths and any secret-like values.

- [ ] **Step 9: Stop the local service and report E1**

Confirm no evidence process remains running. Report the observed results and any failed evidence item; do not advance to E2 until E1 is valid.

---

### Task 2: E2 Build A Minimal Static Evidence Renderer

**Files:**
- Create: `scripts/build_portfolio_evidence.py`
- Test: `tests/test_build_portfolio_evidence.py`
- Create outside Git: `D:\DevData\smartcs\portfolio-evidence\masters\index.html`

**Interfaces:**
- Consumes: `manifest.json` from Task 1.
- Produces: one self-contained static HTML document containing SC-01 through SC-04 as independently capturable sections.

- [ ] **Step 1: Write failing tests for manifest validation and safe rendering**

Cover required evidence IDs, source hashes, the cited-answer gate, visible limitations, HTML escaping, and rejection of secret-like keys or local user-profile paths.

- [ ] **Step 2: Run the focused test and confirm RED**

Run:

```powershell
python -m pytest tests/test_build_portfolio_evidence.py -q
```

Expected: failure because `scripts.build_portfolio_evidence` does not exist.

- [ ] **Step 3: Implement the smallest standard-library renderer**

Use `json`, `html`, `pathlib`, and `hashlib`; add no package. Generate neutral responsive HTML/CSS with fixed board dimensions, print-safe sections, public-demo labels, and no JavaScript dependency.

- [ ] **Step 4: Run the focused test and confirm GREEN**

Run the focused test again and require exit code 0.

- [ ] **Step 5: Render from the approved E1 manifest**

Write the self-contained HTML into `masters`, keeping all figures and statuses identical to the manifest.

- [ ] **Step 6: Commit the renderer and tests**

Commit only source and tests; do not commit generated evidence, secrets, databases, Chroma files, or videos.

---

### Task 3: E2 Export And Visually Verify SC-01 Through SC-04

**Files:**
- Read outside Git: `D:\DevData\smartcs\portfolio-evidence\masters\index.html`
- Create outside Git: `D:\DevData\smartcs\portfolio-evidence\masters\SC-01.png` through `SC-04.png`
- Create outside Git: `D:\DevData\smartcs\portfolio-evidence\exports\SC-01.webp` through `SC-04.webp`

**Interfaces:**
- Consumes: the static evidence page from Task 2.
- Produces: desktop masters and web exports tied to manifest evidence IDs.

- [ ] **Step 1: Open the page in a browser and inspect each board**

Verify 1600px desktop boards and mobile reading at 390px. Check overflow, overlap, text clipping, contrast, and that each board states one main conclusion.

- [ ] **Step 2: Export exact board captures**

Capture SC-01 and SC-04 at 1600x900; capture SC-02 and SC-03 at 1600x1000. Preserve PNG masters and create WebP exports.

- [ ] **Step 3: Compare exports against raw evidence**

Validate every metric, state, short ID, and limitation against the manifest and raw source files. Re-run the secret/path scan over HTML metadata and exported filenames.

- [ ] **Step 4: Run focused and full tests**

Run the renderer test followed by `python -m pytest -q` before declaring E2 complete.

---

### Task 4: E3 Record And Verify The Short Demo

**Files:**
- Create outside Git: `D:\DevData\smartcs\portfolio-evidence\masters\SC-05.mp4`
- Create outside Git: `D:\DevData\smartcs\portfolio-evidence\exports\SC-05.mp4`
- Create outside Git: `D:\DevData\smartcs\portfolio-evidence\exports\SC-05-poster.webp`

**Interfaces:**
- Consumes: one fresh successful run matching the approved evidence boundary.
- Produces: a 60-90 second 1920x1080 master, web encode, poster, and Chinese captions.

- [ ] **Step 1: Prepare a capture-only desktop**

Show only the SmartCS/API/evidence surfaces required by the storyboard. Hide terminals containing environment variables and all unrelated applications.

- [ ] **Step 2: Record one real successful lifecycle**

Capture health, identity boundary, upload and review, cited answer, reindex generation, handoff confirmation and resolution, tenant 403, and evaluation summary in the approved order.

- [ ] **Step 3: Trim and caption without altering evidence**

Only trim idle time and add short title/caption cards. Do not recreate cursor movement, replace API output, or insert a citation absent from the live result.

- [ ] **Step 4: Verify representative frames and metadata**

Inspect beginning, each transition, and ending frames for secrets, user paths, unrelated windows, clipping, blank frames, and readable captions. Verify duration, dimensions, codec, and file size.

---

### Task 5: E4 Review And Portfolio Handoff

**Files:**
- Create outside Git: `D:\DevData\smartcs\portfolio-evidence\handoff.json`
- Modify: `docs/superpowers/specs/2026-07-20-smartcs-portfolio-evidence-package-design.md` only if the user approves wording changes.

**Interfaces:**
- Consumes: approved SC-01 through SC-05 exports and their manifest records.
- Produces: a portfolio-ready handoff contract; the portfolio task remains the only consumer that changes its frontend.

- [ ] **Step 1: Present all exports locally for user review**

Include one-line purpose, dimensions, source commit, and limitations for each asset.

- [ ] **Step 2: Apply only approved evidence wording corrections**

Do not alter measured numbers, state order, failure samples, or boundary claims.

- [ ] **Step 3: Write the handoff contract**

Include project name, one-line positioning, ordering, approved asset paths, alt text, aspect ratios, source commit, verification metrics, limitations, and prohibited claims.

- [ ] **Step 4: Send the structured handoff to portfolio task `019f59c1-a1ab-7820-a310-ff2365afaee8`**

Wait until the user says the portfolio frontend is ready. The receiving task may crop or scale approved exports but may not regenerate evidence or change figures.

- [ ] **Step 5: Final branch verification and integration**

Run the full test suite, perform whole-branch review, and present merge/push options. Generated raw evidence and large media remain outside Git.
