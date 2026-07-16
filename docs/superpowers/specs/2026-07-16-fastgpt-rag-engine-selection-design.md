# SmartCS FastGPT RAG Engine Selection

**Date:** 2026-07-16
**Status:** Approved for proof of concept

## Context

SmartCS is a multi-tenant internal knowledge assistant. Its primary outcome is
that an authenticated employee receives a trustworthy, permission-scoped answer
with sources, or a traceable support handoff. It is not a generic chatbot,
external-customer service, or CRM product.

The existing FastAPI application already owns tenant identity, JWT roles,
auditing, document-domain concepts, and regression tests. Replacing it with a
full application platform would discard useful engineering evidence and create
an unnecessary migration project. Continuing to rebuild every RAG capability by
hand would delay a reliable demonstration.

## Decision

Run a bounded FastGPT proof of concept as a replaceable RAG capability provider.
If it passes the acceptance criteria, SmartCS will integrate it through an
adapter while retaining SmartCS as the system-of-record and governance gateway.

FastGPT is not the public SmartCS product surface and must not become the source
of truth for employee identity, tenant authorization, audit events, support
handoff, or application business state.

## Target Architecture

```text
Employee
  -> SmartCS employee knowledge-assistant API
       -> JWT, tenant and role checks
       -> tenant knowledge-domain mapping
       -> FastGPT adapter
            -> document processing, retrieval, response generation
       -> source normalization, audit, support-handoff decision
  -> source-backed answer or traceable support request
```

### SmartCS Responsibilities

- JWT authentication, tenant isolation, and role checks.
- Mapping a SmartCS tenant to one approved external knowledge-domain/app ID.
- Keeping provider credentials server-side and out of client requests.
- Normalizing provider responses into SmartCS's response contract, including
  source references.
- Recording request metadata, provider failures, and support-handoff records.
- Maintaining security, integration, and tenant-isolation tests.

### FastGPT Responsibilities

- Importing and processing the proof-of-concept documents.
- Knowledge retrieval and answer generation.
- Returning sufficient source metadata for SmartCS to render a traceable answer.
- Optionally providing a visual workflow during operations experimentation.

### Frozen Sales Copilot Lab

The local CRM workflow remains a separate lab. It is not part of the FastGPT
proof of concept and receives no new feature work in this milestone.

## Proof of Concept Scope

Use fictional internal policy documents only. The proof of concept has one
tenant and one small, repeatable corpus. It verifies integration feasibility,
not multi-tenant production deployment.

The proof of concept may create:

- a FastGPT Docker deployment;
- one isolated knowledge base/application;
- a configuration example with placeholders only;
- an adapter spike or API-call test after infrastructure verification.

It must not import real company data, store credentials in Git, replace the
existing RAG path, expose FastGPT administration publicly, or alter CRM code.

## Storage and Deployment Rules

All generated FastGPT and Docker data must live on D:, under:

```text
D:\DevData\smartcs-fastgpt-poc\
```

Before pulling images, Docker Desktop's disk-image location must be checked. If
it points to C:, it must be changed through Docker's supported settings before
the proof of concept begins. Do not manually move active Docker data folders.

The proof of concept uses pinned images or documented versions, project-local
configuration, and fictional data. Secrets remain in a local ignored `.env`
file.

## Acceptance Criteria and Go/No-Go Gate

The FastGPT route is approved for adapter implementation only when all of the
following are demonstrated and recorded:

1. A fictional document can be ingested reproducibly from the documented setup.
2. A representative employee question returns an answer with usable source
   metadata that SmartCS can normalize.
3. The provider can be called through a server-side API credential; no provider
   credential reaches a browser or repository.
4. SmartCS can select the provider knowledge-domain/app solely from server-side
   tenant mapping, not a client-provided identifier.
5. Startup, shutdown, and data locations are documented and all large generated
   data stays on D:.
6. The selected FastGPT version and its license/attribution requirements are
   recorded and compatible with a public portfolio demonstration.

Any failed gate means no integration. The proof of concept is stopped and the
existing SmartCS retrieval path remains the implementation baseline.

## Integration Boundary After a Successful Proof of Concept

Later implementation should introduce one provider interface, for example a
`KnowledgeAnswerProvider`, with a FastGPT adapter behind it. The Assistant API
must depend on the provider interface, not FastGPT response shapes or internal
database structures.

The first adapter supports only answer generation and normalized citations.
Document lifecycle synchronization, provider failover, and visual workflow
editing are explicitly deferred until the primary path is reliable.

## Risks and Controls

| Risk | Control |
| --- | --- |
| Duplicate tenant models across systems | SmartCS owns mapping and authorization; FastGPT IDs are server-side configuration. |
| Provider API cannot return trustworthy citations | Fail the gate; do not hide the limitation behind generated prose. |
| Docker fills C: | Check Docker's supported disk-image location before image pulls and bind project data to D:. |
| License/attribution conflict | Record the exact version and terms before any public demonstration. |
| Provider outage | Preserve the current SmartCS RAG route until an explicit fallback design is approved. |
| Scope creep into a generic workflow platform | Limit the proof of concept to ingestion, one question, sources, and API integration. |

## Non-Goals

- Replacing SmartCS authentication, admin APIs, or audit records with FastGPT.
- Running a public SaaS service or importing non-fictional enterprise data.
- Replatforming the Sales Copilot Lab.
- Building every FastGPT workflow feature into SmartCS.
- Claiming production readiness based on a local proof of concept.
