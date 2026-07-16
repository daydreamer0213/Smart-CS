# SmartCS Product Domain Boundary

**Date:** 2026-07-16
**Status:** Approved

## Decision

SmartCS is a multi-tenant internal knowledge assistant for enterprise employees.
Its primary user is an authenticated employee, not an external customer and not a
sales representative operating a CRM.

The existing local CRM workflow remains in this repository as an isolated
`Sales Copilot Lab`. It is retained as evidence of controlled Agent tool use,
confirmation-gated writes, idempotency, and audit logging. It is not part of the
SmartCS primary product, primary demo, or primary README narrative.

## Product Boundary

### Knowledge Assistant (primary product)

The primary path is:

1. An employee authenticates within a tenant.
2. The assistant retrieves only tenant- and role-authorized enterprise knowledge.
3. The response returns traceable source references.
4. When knowledge is insufficient or a case requires a person, the system creates
   a trackable support handoff instead of inventing an answer.

The product success criterion is not generic conversation quality. It is that an
employee can obtain a trustworthy, permission-scoped, source-backed answer or a
reliable support handoff.

### Sales Copilot Lab (secondary module)

The local CRM models and controlled workflow remain separate from the knowledge
assistant's product surface:

- CRM reads and action drafts are limited to authorized sales roles.
- A model may prepare a change but cannot write business data directly.
- Confirmation rechecks authorization, handles idempotency, and records an audit
  event.

This module is frozen for the current SmartCS milestone. It may later become an
independent Sales Copilot project if there is a dedicated product goal.

## Architecture Boundary

SmartCS remains a modular monolith for this milestone. It shares platform
capabilities while separating domain-specific APIs, tools, tests, and
documentation.

| Shared platform | Knowledge Assistant | Sales Copilot Lab |
| --- | --- | --- |
| Tenants, JWT, roles, audit primitives, database access, observability | Documents, knowledge, hybrid retrieval, citations, support handoff | CRM reads, action drafts, confirmation, idempotency |

No new repository, microservice, database split, or API rename is required now.
The current `/assistant` path remains the employee knowledge-assistant entry.
The protected `/business` path is explicitly a secondary transition/lab surface,
not a public SmartCS entry point.

## Scope for the Next Product Milestone

Prioritize the knowledge assistant:

- response-level document and FAQ citations;
- a real support-handoff record and status lifecycle;
- document authorization, lifecycle, and observable ingestion failures;
- RAG quality and tenant-isolation regression cases.

Do not expand CRM objects, sales workflows, pipeline automation, or external CRM
integrations in this milestone.

## Consequences

- The README, demo, and interview narrative will lead with the knowledge assistant.
- Sales Copilot remains available only as an optional technical deep dive.
- Shared authentication and audit mechanisms are retained, so existing CRM work is
  not discarded.
- Future implementation work must state which domain it belongs to before coding.

## Acceptance Criteria

The boundary is considered correctly reflected when:

1. The primary README, demo, and API entry describe the internal knowledge
   assistant without presenting CRM as a core capability.
2. Knowledge-assistant tests do not require CRM data or sales roles.
3. CRM tests and endpoints are labelled as Sales Copilot Lab coverage.
4. New Agent tools are assigned to one domain and have explicit role and audit
   requirements.

## Non-Goals

- Splitting SmartCS into microservices or a second repository.
- Deleting tested CRM code solely to make the repository smaller.
- Building a generic CRM, external-customer chatbot, or sales automation platform.
