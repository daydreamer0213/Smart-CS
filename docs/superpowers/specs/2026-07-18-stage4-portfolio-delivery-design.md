# SmartCS Stage 4 Portfolio Delivery Design

**Date:** 2026-07-18

**Status:** Approved for written specification review

## Goal

Turn the completed SmartCS HR Agent foundation into a reproducible interview
delivery package. This stage changes project materials and the live demo only;
it does not add a new product capability.

## Product Positioning

SmartCS is a multi-tenant enterprise HR service Agent foundation for internal
employees. It provides governed HR knowledge retrieval, document-level role
boundaries, evidence-backed answers, confirmation-gated human handoff, minimal
handoff lifecycle management, and auditable backend controls.

The legacy Sales Copilot remains an isolated `/business/*` lab for regression
coverage. It is not part of the primary architecture, demo, resume bullet, or
first interview explanation.

## Delivery Strategy

Use a hybrid demonstration strategy:

1. Automated tests are the deterministic engineering verification. The stage
   acceptance gate remains the full pytest suite in the documented Conda
   environment.
2. `scripts/demo_enterprise_flow.py` is a live, fictional-data demonstration
   that uses the configured chat and embedding models. It demonstrates Agent
   behavior rather than trying to replace automated verification.
3. Documentation explicitly distinguishes the two, so an interviewer sees
   both reproducibility and real model orchestration.

## Live Demo Contract

The script assumes a running local API and creates a uniquely named fictional
tenant. It performs the following public API workflow:

```text
health check
  -> owner creates a fictional HR tenant
  -> owner creates an employee and HR administrator
  -> owner uploads employee-visible HR policy document
  -> employee asks a covered policy question
  -> response contains source citations
  -> employee asks a cross-border exception and explicitly requests HR help
  -> Agent returns a pending handoff draft
  -> employee confirms the draft
  -> HR administrator assigns and resolves the request
  -> employee reads only their own request status
  -> another tenant is denied access
```

The script must stop with a concise configuration error if the running API
cannot call the configured chat or embedding model. It must not silently treat
an LLM failure as a successful HR demonstration.

## Documentation Contract

The following materials are the source of truth for different audiences:

| Material | Audience | Required message |
| --- | --- | --- |
| `README.md` | Recruiter, reviewer, developer | HR Agent positioning, architecture, local start, test, and live demo entry points. |
| `docs/operations/local-hr-agent-demo.md` | Developer / interviewer | Conda path, online Alembic bootstrap, required model variables, API start, demo execution, cleanup, and known limitations. |
| `docs/interview/SMARTCS_DEMO_SCRIPT.md` | Interviewer | Three-minute Chinese narration mapped to visible demo steps. |
| `docs/interview/SMARTCS_INTERVIEW.md` | Interview preparation | Resume bullet, technical explanation, trade-offs, and expected follow-up questions. |
| `docs/interview/SMARTCS_DELIVERY_PACKAGE.md` | Portfolio reviewer | Final acceptance checklist, proof points, and honest scope boundary. |

All materials must use the actual project root `D:\2026.07.09\AAA\smart-cs`
and the documented Conda Python
`D:\2026.07.09\conda-envs\smart-cs\python.exe`. They must state that a
greenfield database uses online `alembic upgrade head`; `--sql` output is only
for the legacy document-table path.

## Demo Data and Access Rules

- Use only fictional Beichen Technology HR policies and synthetic users.
- Upload the covered policy with `audience_roles=["employee"]` or an empty
  list where all roles should see it; the script prints the chosen boundary.
- The covered question must show at least one source in the Assistant response.
- The exception question must be outside the policy and explicitly request
  human HR help, making a handoff draft the expected safe result.
- The script validates response shape, source presence, pending-draft state,
  confirmation, assignment, resolution, employee-scoped status, and
  cross-tenant denial. It does not assert model wording.

## Non-Goals

- No new Agent, model provider, reranker, generic workflow engine, or FastGPT
  runtime integration.
- No SSO, HRIS, approval engine, notifications, SLA management, or frontend
  redesign.
- No claim that SmartCS is a production commercial HR SaaS.
- No new Python dependency unless a current standard-library or installed
  dependency cannot complete the documented demo contract.

## Validation

1. Run the full test suite with the documented Conda Python.
2. Run an online Alembic migration against a disposable SQLite database on
   `D:\DevData` and confirm `documents`, `document_chunks`, and
   `audience_roles` exist.
3. Run a manual live demo with configured models and capture only status,
   IDs, sources, and lifecycle state in terminal output; never print secrets.
4. Check that all material uses the HR foundation positioning and no primary
   README/demo text describes CRM as the user-facing product.

## Definition of Done

- A recruiter can identify SmartCS as a governed HR Agent from the README.
- A reviewer can start the project and run the live demo from one runbook.
- An interviewer can follow a three-minute Chinese script that demonstrates
  source-backed answer, role boundary, confirmation-gated handoff, lifecycle,
  and tenant isolation.
- The written narrative matches the implemented Stage 1-3 behavior and its
  stated limitations.
