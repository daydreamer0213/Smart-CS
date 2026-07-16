# SmartCS Project Notes

## Positioning

SmartCS is an enterprise AI application engineering sample for a Python / RAG /
Agent backend role.

It should be presented as:

- multi-tenant enterprise employee Agent backend.
- tenant-scoped RAG and document import.
- role-scoped enterprise knowledge and CRM Skills.
- confirmation-gated CRM writes.
- JWT and API key authentication.
- audit logs, idempotency, and test coverage.
- observable and testable Python backend.

It should not be presented as a simple FAQ chatbot or a finished commercial
SaaS.

## Real Local Paths

Project root:

```text
D:\2026.07.09\AAA\smart-cs
```

Python:

```text
D:\2026.07.09\conda-envs\smart-cs\python.exe
```

conda:

```text
D:\2026.07.09\conda\Scripts\conda.exe
```

Large caches:

```text
D:\2026.07.09\smartcs-cache\pip
D:\2026.07.09\smartcs-cache\huggingface
D:\2026.07.09\smartcs-cache\torch
```

Old paths such as `D:\AAA`, `D:\conda-envs`, and `D:\conda` are historical.

## Current Status

Completed:

- environment restored on the new machine.
- D-drive dependency/cache path documented.
- document import and governed RAG exist.
- JWT auth and multi-tenant identity boundary implemented.
- owner/admin/agent/employee roles implemented.
- unified employee Agent route added: `/api/v1/{tenant_slug}/assistant/*`.
- role-scoped knowledge and CRM Skills implemented.
- local CRM sales-assistant MVP added.
- CRM writes are confirmation-gated, idempotent, and audited.
- the unauthenticated `/chat` route is not mounted; `/assistant` is the only
  employee-facing Agent entry, while `/business` remains JWT-protected transition coverage.
- offline hash embedding demo flow verified.
- README, interview notes, final pitch, and demo script added.

## Auth And Skill Model

- owner self-registers and creates a tenant.
- owner/admin credentials are required to create users in an existing tenant.
- employee receives knowledge access only.
- agent/admin/owner receive knowledge + CRM read + CRM prepare-change Skills.
- admin APIs support both Bearer JWT and `X-Admin-Key`.
- both JWT and API key admin paths enforce tenant boundary by comparing the
  credential tenant with the URL `tenant_slug`.
- CRM writes are not exposed as direct Agent tools; the Agent creates a draft,
  then the confirmation endpoint performs the write.

Important files:

- `app/api/auth.py`
- `app/api/assistant.py`
- `app/api/business.py`
- `app/api/admin/auth.py`
- `app/core/agent/business_agent.py`
- `app/services/assistant_service.py`
- `app/services/business_service.py`
- `app/models/user.py`
- `app/models/crm.py`
- `app/core/embedding/hash_provider.py`
- `tests/test_auth.py`
- `tests/test_assistant_api.py`
- `tests/test_assistant_agent.py`
- `tests/test_business_api.py`
- `docs/interview/SMARTCS_DELIVERY_PACKAGE.md`
- `docs/interview/SMARTCS_FINAL_PITCH.md`

## Core Commands

```powershell
cd D:\2026.07.09\AAA\smart-cs

D:\2026.07.09\conda-envs\smart-cs\python.exe -m pytest tests/ -v

D:\2026.07.09\conda-envs\smart-cs\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

D:\2026.07.09\conda-envs\smart-cs\python.exe scripts\demo_enterprise_flow.py
```

For offline demos without external embedding quota:

```powershell
$env:EMBEDDING_PROVIDER="hash"
```

## Next Practical Step

Use `docs/interview/SMARTCS_DELIVERY_PACKAGE.md` as the job-search entry point.
For role-specific resume wording, use `docs/interview/SMARTCS_FINAL_PITCH.md`.
For live demo prep, use `docs/interview/SMARTCS_DEMO_SCRIPT.md`.

Keep changes small. Do not start a new project. Do not expand features for
trend-chasing. The goal is a credible enterprise AI backend sample.
