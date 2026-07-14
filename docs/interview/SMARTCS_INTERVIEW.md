# SmartCS Interview Notes

## Project Positioning

SmartCS is an enterprise AI application engineering sample:

- multi-tenant enterprise employee Agent backend.
- tenant-scoped RAG and document import.
- role-scoped enterprise knowledge and CRM Skills.
- confirmation-gated CRM writes.
- audit logs and idempotent confirmation.
- admin governance APIs.
- JWT and API key authentication.
- tests for auth, tenant isolation, RAG, agent behavior, CRM safety, streaming,
  and security cases.

The point is not "I made a chatbot." The point is "I can build the backend
engineering around an enterprise Agent workflow."

## Practical Business Scenarios

### Internal employee assistant

Employees can ask about policies, processes, product rules, or field meanings.
The assistant retrieves enterprise knowledge under the current tenant and role.
Some knowledge entries can be role-restricted.

### Sales assistant

Sales users can query local CRM facts such as customers, contacts, leads,
opportunities, and follow-up tasks. The assistant must use CRM Skills for CRM
facts instead of inventing answers.

### Controlled business actions

The Agent can prepare lead/task changes, but it cannot directly write business
data. It creates a pending action draft; a separate confirmation endpoint
revalidates permissions, handles idempotency, performs the write, and records an
audit log.

### Multi-tenant AI governance

Each tenant has isolated users, knowledge, documents, CRM demo data, admin APIs,
and credentials. SmartCS treats tenant isolation as a backend contract, not a UI
filter.

## Resume Bullets

- Built a FastAPI-based multi-tenant enterprise employee Agent with RAG,
  document import, role-scoped CRM Skills, confirmation-gated writes, audit
  logs, admin APIs, and automated tests.
- Designed tenant and role isolation across knowledge, documents, CRM facts,
  admin APIs, API keys, JWT users, and Agent Skills.
- Implemented JWT authentication with owner tenant creation, authorized
  tenant-member creation, owner/admin/agent/employee roles, token refresh, and
  backward-compatible API key support.
- Added a local CRM sales-assistant MVP with customer overview, lead/task action
  drafts, explicit confirmation, duplicate-lead protection, idempotent
  confirmation, and audit logs.
- Covered key backend behavior with pytest cases for RAG retrieval, Agent
  tools, role-scoped Skills, controlled CRM writes, SSE streaming, security,
  tenant isolation, and JWT boundaries.

## 30-Second Pitch

SmartCS is my Python AI backend sample. It is a multi-tenant enterprise employee
Agent: users authenticate first, then the backend exposes only the Skills their
role permits. Employees can query enterprise knowledge; sales users can query
CRM facts and prepare business changes. Actual writes require explicit
confirmation, permission revalidation, idempotency, and audit logs.

## 2-Minute Pitch

I did not want SmartCS to be another FAQ chatbot demo, so I shaped it around
enterprise Agent concerns. A company using this kind of system cares about
whether tenant data is isolated, whether employees see only the right Skills,
whether knowledge can be governed, whether CRM facts come from tools, and
whether business writes are safe.

The backend is FastAPI. Tenants own users, knowledge, documents, conversations,
admin API keys, and local CRM demo records. The RAG layer combines document
import, chunking, vector retrieval, BM25 search, and role-scoped knowledge
visibility. The Agent layer exposes knowledge and CRM tools based on the user
role.

The CRM workflow is deliberately controlled: the Agent can create a draft for a
lead or follow-up task, but a separate confirmation endpoint performs the write.
That confirmation path revalidates permissions, supports idempotency, handles
conflicts, and writes an audit log. This is the difference between a demo
chatbot and an enterprise AI backend.

## Deep-Dive Talking Points

### Why role-scoped Skills?

Enterprise assistants should not expose the same abilities to every employee.
SmartCS gives `employee` knowledge access only, while `agent/admin/owner` can
also use CRM read and prepare-change Skills. Tool selection is a backend
decision, not a prompt-only convention.

### Why confirmation-gated writes?

LLMs should not directly mutate business data. SmartCS separates intent from
execution: the Agent drafts an action, the user confirms it, and the backend
revalidates and writes. This makes the workflow auditable and safer.

### Why JWT and API key together?

JWT is for human operators and employee sessions. API key is retained for
machine-to-machine scripts and admin automation. Both paths validate tenant
boundaries.

### What was the important JWT security issue?

The first draft allowed a request body to choose `role=admin` for an existing
tenant if the caller knew the tenant slug. I treated that as a real tenant
boundary bug, reproduced it with a failing test, then fixed the root cause:
admin/agent/employee creation for an existing tenant now requires same-tenant
owner/admin JWT or same-tenant API key.

### How is this different from DocMind or KnowledgeFlow?

DocMind proves RAG collaboration experience. KnowledgeFlow proves independent
multi-agent project ability. SmartCS proves Python AI backend engineering:
auth, tenant boundaries, RAG, role-scoped Agent Skills, controlled business
writes, admin APIs, tests, and operational paths in one service.

### What would you improve next?

- Add invitation-based member onboarding.
- Add CI/CD and deployment packaging.
- Add production observability dashboards and tracing.
- Harden secrets and environment management.
- Replace fictional local CRM data with a real CRM integration adapter.

## Demo Path

1. Start the app and health check.
2. Register an owner and create a tenant.
3. Use the owner JWT to create an agent and an employee.
4. Create enterprise knowledge and import a document.
5. Call `/api/v1/{tenant_slug}/assistant/chat` as the employee.
6. Show enabled Skills are role-scoped.
7. Show admin knowledge/documents/analytics.
8. Show agent admin access is forbidden.
9. Show cross-tenant admin access is forbidden.

Use:

```powershell
$env:EMBEDDING_PROVIDER="hash"
& D:\2026.07.09\conda-envs\smart-cs\python.exe scripts\demo_enterprise_flow.py
```

## Honest Boundaries

- This is not a production SaaS deployment yet.
- The local CRM is fictional demo data, not a complete CRM product.
- The UI is not the main proof point.
- Full answer quality depends on configured LLM and embedding providers.
- The current value is backend engineering maturity around an enterprise Agent
  workflow.
