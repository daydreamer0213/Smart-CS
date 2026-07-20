# SmartCS Four-Module Portfolio Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the archived SC-05 video handoff with four traceable, responsive content modules that the portfolio task can integrate without inventing product UI or production claims.

**Architecture:** Extend the existing evidence-to-material generator rather than creating a second frontend. The SmartCS package produces machine-readable module content, direct factual copy, and a final handoff contract; the receiving portfolio task owns HTML, CSS, interaction, and visual integration.

**Tech Stack:** Python 3.12 standard library, JSON, Markdown, pytest, existing SmartCS evidence manifest.

## Global Constraints

- Keep generated materials and archived media under `D:\DevData\smartcs\portfolio-evidence`; do not copy large assets to `C:`.
- Do not create HTML, CSS, React components, product screenshots, or a SmartCS frontend in this repository.
- Use direct factual Chinese copy; avoid repeated contrast formulas such as "not X, but Y", "the real problem", or "cannot only".
- Preserve source commit, evidence references, public fictional data classification, measured values, failed queries, and limitations.
- Keep the archived SC-05 video, poster, captions, and keyframes out of the approved handoff asset list.
- The receiving portfolio task may change layout and shorten copy, but may not change facts, metrics, state order, or limitations.

---

### Task 1: Finalize The Archive Boundary

**Files:**
- Modify: `docs/superpowers/plans/2026-07-20-smartcs-portfolio-evidence-package.md`
- Modify: `docs/superpowers/specs/2026-07-20-smartcs-portfolio-evidence-package-design.md`
- Create outside Git: `D:\DevData\smartcs\portfolio-evidence\archive\2026-07-20-sc-05-video\README.md`

**Interfaces:**
- Consumes: verified SC-05 outputs and `video-manifest.json`.
- Produces: an archive with unchanged hashes and no SC-05 assets in formal `masters` or `exports` directories.

- [x] Move the master, web export, poster, captions, keyframes, and video manifest into the dated archive directory without deleting them.
- [x] Verify the four hashed outputs still match `video-manifest.json`.
- [x] Confirm the source runtime logs, RAG report, and narrative slide references remain in the E3 run directory.
- [x] Update the active plan and design notes so the video cannot be mistaken for an approved handoff asset.

### Task 2: Generate Four Responsive Content Modules

**Files:**
- Modify: `tests/test_build_portfolio_handoff.py`
- Modify: `scripts/build_portfolio_handoff.py`
- Generate outside Git: `D:\DevData\smartcs\portfolio-evidence\materials\portfolio-modules.json`
- Generate outside Git: `D:\DevData\smartcs\portfolio-evidence\materials\portfolio-copy.md`
- Generate outside Git: `D:\DevData\smartcs\portfolio-evidence\materials\README.md`

**Interfaces:**
- Consumes: validated E1 manifest, `project-facts.json`, and six evidence-backed claims.
- Produces: `portfolio-modules.json` with exactly four ordered modules and direct factual page copy.

- [x] Extend the existing output-contract test to require `portfolio-modules.json` and assert module IDs `overview`, `knowledge-governance`, `agent-boundary`, and `engineering-quality`.
- [x] Assert every module has a title, summary, claim IDs, evidence-backed proof items, mobile presentation guidance, alt text, and a visible limitation.
- [x] Add a copy-style regression assertion that rejects repeated contrast-formula phrases from generated page copy and module headings.
- [x] Implement the minimal generator changes, reusing existing facts and claim references rather than duplicating evidence parsing.
- [x] Run `python -m pytest tests/test_build_portfolio_handoff.py -q` and confirm all handoff tests pass.
- [x] Regenerate the materials directory from `D:\DevData\smartcs\portfolio-evidence\manifest.json`.

### Task 3: Produce And Validate The Final Handoff Contract

**Files:**
- Modify: `tests/test_build_portfolio_handoff.py`
- Modify: `scripts/build_portfolio_handoff.py`
- Generate outside Git: `D:\DevData\smartcs\portfolio-evidence\handoff.json`
- Generate outside Git: `D:\DevData\smartcs\portfolio-evidence\materials\portfolio-modules.md`

**Interfaces:**
- Consumes: generated facts, claims, module contract, and relative visual-reference identifiers.
- Produces: a single handoff contract for portfolio task `019f59c1-a1ab-7820-a310-ff2365afaee8`.

- [x] Add contract assertions for module order, source commit, data classification, relative material paths, prohibited claims, archived-video exclusion, and frontend ownership.
- [x] Generate a concise Markdown integration guide covering desktop composition, mobile stacking, semantic headings, accessible metric labels, and evidence-link handling.
- [x] Generate `handoff.json` without absolute local paths, credentials, tokens, HTML, or CSS.
- [x] Scan all generated text for sensitive keys, absolute local paths, replacement characters, and prohibited AI-template phrases.
- [x] Run the focused handoff tests and then the full `python -m pytest -q` suite.

### Task 4: Transfer And Verify Portfolio Integration

**Files:**
- Consume in portfolio task: `D:\DevData\smartcs\portfolio-evidence\handoff.json`
- Consume in portfolio task: `D:\DevData\smartcs\portfolio-evidence\materials\portfolio-modules.json`
- Consume in portfolio task: `D:\DevData\smartcs\portfolio-evidence\materials\portfolio-modules.md`

**Interfaces:**
- Consumes: the validated SmartCS handoff contract.
- Produces: a SmartCS project section inside the existing portfolio frontend; no SmartCS repository frontend changes.

- [ ] Send the contract and integration constraints to portfolio task `019f59c1-a1ab-7820-a310-ff2365afaee8`.
- [ ] Require the receiving task to preserve the current portfolio visual system while rebuilding the four modules responsively, not embedding dense 16:9 slide screenshots.
- [ ] Require browser verification at desktop and 375px mobile widths for readability, overflow, focus order, alt text, and archived-video absence.
- [ ] Review the receiving task's completion report against `handoff.json`; correct only factual or contract violations.
- [ ] Mark E4 and the SmartCS portfolio evidence goal complete when the handoff package and receiving-task verification both pass.
