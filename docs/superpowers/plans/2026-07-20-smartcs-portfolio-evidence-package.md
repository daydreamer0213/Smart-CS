# SmartCS Portfolio Evidence Package Implementation Plan

> **Scope correction (2026-07-20):** SmartCS produces traceable project materials. The portfolio task owns page layout, styling, interaction, and final presentation. This plan does not create a second frontend.

**Goal:** Produce a redacted, independently verifiable SmartCS material package and hand it to the portfolio task without inventing product UI or production claims.

**Architecture:** Run SmartCS against fresh fictional HR data, preserve sanitized raw evidence, validate it with SHA-256 hashes, and derive neutral JSON/Markdown materials. A later live recording supplies real visual frames. The receiving portfolio task consumes the facts and media but controls all frontend presentation.

**Tech Stack:** Python 3.11, FastAPI, Alembic, pytest, PowerShell, standard-library JSON/Markdown generation, FFmpeg only if already available.

## Global Constraints

- Keep generated evidence, databases, logs, screenshots, and video under `D:\DevData\smartcs\portfolio-evidence`.
- Use only fictional Beichen Technology data and `example.com` or `example.test` identities.
- Never export API keys, JWTs, passwords, cookies, authorization headers, `.env` contents, storage keys, physical document paths, or unrelated desktop windows.
- Every public claim must identify its source Git commit, manifest pointer, or hashed raw evidence file.
- A policy answer without a structured source and matching `[source:<id>]` token is not valid cited-answer evidence.
- Keep visible limitations: curated corpus, HashEmbedding is non-semantic, BM25 contribution 11, vector contribution 0, and `payroll-contact` is the retained failure.
- Do not add an HRIS integration, Agent tool, SmartCS frontend, portfolio frontend dependency, visual framework, or generated product screenshot.
- Preserve existing user changes in the main worktree; implementation runs in `codex/portfolio-evidence-package`.

---

## E1: Reproduce And Collect Raw Evidence

**Status:** Complete.

**Git files:**

- `scripts/demo_enterprise_flow.py`
- `tests/test_demo_enterprise_flow.py`

**Generated evidence:**

- `D:\DevData\smartcs\portfolio-evidence\raw\20260720T072602Z-12c374a\*`
- `D:\DevData\smartcs\portfolio-evidence\manifest.json`

**Observed acceptance evidence:**

- [x] Fresh Alembic database initialized on D drive.
- [x] SmartCS health returned HTTP 200.
- [x] Enterprise demo produced governed upload, approved current snapshot, cited answer, reindex generation, HR handoff lifecycle, and cross-tenant 403.
- [x] Retrieval gate passed with Recall@3 91.67%, MRR 91.67%, recalled-source provenance 100%, BM25 11, vector 0, and retained failure `payroll-contact`.
- [x] Clean full regression completed with 396 passed, 4 skipped, 1 warning, and 0 failed.
- [x] Raw outputs were sanitized, hashed, and indexed in the manifest.
- [x] Local services were stopped after collection.

---

## E2: Build And Verify Neutral Materials

**Status:** Complete.

**Git files:**

- Create: `scripts/build_portfolio_handoff.py`
- Create: `tests/test_build_portfolio_handoff.py`
- Modify: this plan only; do not modify the portfolio frontend.

**Generated materials:**

- `D:\DevData\smartcs\portfolio-evidence\materials\README.md`
- `D:\DevData\smartcs\portfolio-evidence\materials\project-facts.json`
- `D:\DevData\smartcs\portfolio-evidence\materials\claims.json`
- `D:\DevData\smartcs\portfolio-evidence\materials\portfolio-copy.md`

### Material contract

`project-facts.json` contains machine-readable positioning, capabilities, metrics, regression results, data boundary, source commit, and limitations.

`claims.json` contains six approved claim candidates. Each item has:

- stable claim ID;
- factual claim;
- business value;
- manifest pointer or hashed raw evidence reference;
- explicit limitation.

`portfolio-copy.md` contains one-line positioning, project introduction, resume bullets, interview explanation, approved metrics, and prohibited claims. It is copy material, not final page copy.

### Verification steps

- [x] Write a failing test before the generator exists.
- [x] Implement the smallest standard-library generator; add no dependency.
- [x] Reject unsafe citations, sensitive field names, local paths, missing files, and changed source hashes.
- [x] Generate all four neutral material files from the approved E1 manifest.
- [x] Scan generated files for credentials and local absolute paths.
- [x] Review every claim against the raw demo, retrieval report, and pytest output.
- [x] Run focused and full regression suites.
- [x] Commit the E2 generator, tests, and corrected plan.

### Explicit non-deliverables

- No HTML, CSS, React component, page route, dashboard mockup, or visual design system.
- No claim that an evidence diagram is a SmartCS product screenshot.
- Draft evidence-board images created before this correction are not part of the approved handoff.

---

## E3: Build And Verify The Runtime Evidence Film

**Status:** Completed and archived after user review on 2026-07-20. The film is not an approved portfolio handoff asset.

**Archived media:**

- `D:\DevData\smartcs\portfolio-evidence\archive\2026-07-20-sc-05-video`
- The verified runtime logs, retrieval report, and reusable slide references remain in the isolated E3 run directory.

### Presentation boundary

- Present only facts extracted from a successful SmartCS API run and fresh retrieval evaluation.
- Use a neutral evidence narrative instead of a terminal recording or invented product UI.
- Show the public fictional data label and never show credentials, authorization headers, local paths, or private material.
- Preserve measured states, response text, citation IDs, metrics, and limitations; do not recreate or improve runtime results.

### Required lifecycle

1. Service health and fictional tenant context.
2. Document upload resulting in `ready + pending_review`.
3. Owner review resulting in `approved + current`.
4. Employee question with matching structured source and `[source:<id>]` token.
5. Reindex generation switch.
6. Handoff draft, employee confirmation, open, assigned, resolved.
7. Cross-tenant 403 and retrieval-evaluation summary.

### Acceptance

- [x] 79-second 1920x1080 master built from one valid run and labeled as a runtime evidence replay.
- [x] H.264 `yuv420p` web encode, AAC audio track, Chinese subtitle track, poster, and eight real keyframes produced.
- [x] Representative frames inspected for secrets, paths, clipping, blank frames, and caption readability.
- [x] Duration, dimensions, codecs, file sizes, source/output SHA-256 values, and source commit recorded.

---

## E4: User Review And Portfolio Handoff

**Status:** Completed on 2026-07-20. The four-module handoff was integrated into the portfolio frontend and independently verified at desktop and 375px widths.

**Generated contract:**

- `D:\DevData\smartcs\portfolio-evidence\handoff.json`

### Review and handoff

- [x] Replace the video-first handoff with four responsive content modules: overview, knowledge governance and citation, controlled Agent action and tenant boundary, engineering quality and limitations.
- [x] Rewrite contrast-heavy copy such as "not X, but Y" into direct factual statements.
- [x] Write the final contract with module order, approved copy, evidence references, source commit, metrics, limitations, and prohibited claims.
- [x] Do not hand off the archived video, video poster, or video keyframes as required portfolio assets.
- [x] Send the structured contract to portfolio task `019f59c1-a1ab-7820-a310-ff2365afaee8` after the user approved immediate integration.
- [x] Run final branch verification and record the integration result for merge/push review.

The receiving task may redesign the presentation, crop approved media, and shorten copy. It may not regenerate evidence, invent product screens, change figures, remove data-boundary labels, or hide known limitations.
