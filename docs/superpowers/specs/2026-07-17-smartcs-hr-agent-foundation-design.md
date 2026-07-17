# SmartCS HR Agent Foundation Design

**Date:** 2026-07-17
**Status:** Draft for written review
**Supersedes:** The primary product framing in the 2026-07-16 SmartCS domain-boundary design

## Decision

SmartCS is an enterprise HR service Agent foundation for internal employees. It is not an external customer chatbot, a generic workflow builder, or a complete HR SaaS product.

The foundation provides tenant-aware identity, role checks, conversational Agent orchestration, governed tool execution, explicit confirmation for writes, source traceability, audit records, and testable business boundaries. Future HR capabilities are added as bounded Skills rather than as standalone chatbots.

The first release delivers two Skills:

1. **HR Knowledge Skill:** answers policy and process questions from authorized HR documents with traceable source references.
2. **HR Support Skill:** drafts and, after explicit employee confirmation, creates a human-support request when the available knowledge is insufficient, ambiguous, or outside the assistant's authority.

## Product Problem

Employees repeatedly search fragmented HR policy documents or interrupt HR specialists with routine questions. A generic language-model response is unsafe when the answer is not grounded in the current policy, the employee lacks access to the relevant document, or the question concerns an exception such as a cross-border employment arrangement.

SmartCS gives an authenticated employee one reliable entry point. It returns a source-backed answer when it has adequate evidence and routes unresolved cases to a human with the relevant context. HR can see document-ingestion health and unresolved questions that show a gap in policy coverage.

## Primary Users

| User | Need | SmartCS responsibility |
| --- | --- | --- |
| Employee | Find an applicable HR policy or get help. | Restrict data to the employee's tenant and permitted audience; answer with sources or offer handoff. |
| HR administrator | Publish and maintain policy knowledge. | Import documents, inspect ingestion status, and review support requests. |
| HR specialist | Resolve policy exceptions. | Receive a structured support request and update its lifecycle state. |

## First-Release Scenario

The reproducible demonstration uses fictional data for a company named Beichen Technology.

1. An HR administrator imports an annual-leave policy document.
2. An authenticated employee asks how many paid-leave days they receive and how far in advance they must apply.
3. The Agent uses the HR Knowledge Skill and returns the policy answer with a named source section.
4. The employee asks how cross-border employment affects leave. The policy does not cover this exception.
5. The Agent explains that it has no authoritative source, prepares a support request, and creates it only after the employee confirms.
6. The HR administrator views and resolves the request. An employee in another tenant cannot read the Beichen policy or request.

## Agent Design

SmartCS is a governed, stateful tool-calling Agent. It is not a fixed retrieve-then-answer workflow and it is not an unrestricted autonomous agent.

For each employee request, the Agent receives the authorized conversation context, the current user's role, and the allowed HR Skill catalog. It chooses a next action based on the request and prior tool observations:

| Skill | Purpose | Write behavior |
| --- | --- | --- |
| search_hr_knowledge | Find authorized policy or process passages and citations. | Read-only. |
| ask_clarifying_question | Resolve a vague question before attempting a conclusion. | Read-only. |
| draft_handoff | Explain why the case needs a person and prepare a structured draft. | Read-only. |
| create_handoff | Persist a support request after the employee confirms the draft. | Confirmation-gated write. |
| get_handoff_status | Return the current user's visible request status. | Read-only. |

The normal loop is:

~~~text
Employee request
  -> authentication and tenant/role check
  -> Agent selects an authorized Skill
  -> observes typed tool output
  -> answers with citations, asks a clarifying question, or prepares handoff
  -> server-side policy validation
  -> response, confirmed write, and audit record
~~~

Hard controls remain deterministic:

- Authentication, tenant isolation, document audience filtering, and role checks occur before an Agent can access HR data.
- A policy conclusion must identify an authorized source. An unsupported answer cannot be presented as a definitive HR rule.
- The Agent can prepare but cannot directly persist a support request. The employee explicitly confirms the draft first.
- Every tool call and completed support-request write records the actor, tenant, result code, and reason without logging sensitive business payloads.

## Architecture

SmartCS stays a modular FastAPI monolith for this milestone.

~~~text
Employee UI
  -> SmartCS API
       -> JWT, tenant, role, and rate-limit checks
       -> HR Service Agent
            -> HR Knowledge Skill
                 -> document import state plus BM25/vector retrieval
            -> HR Support Skill
                 -> handoff records and lifecycle
       -> response citations plus audit events

HR Admin UI
  -> document import and status APIs
  -> support-handoff list and lifecycle APIs
~~~

The existing FastAPI, JWT, tenant, document-import, hybrid retrieval, Agent, SSE, admin, logging, and regression-test foundations remain the primary engineering evidence.

The former CRM workflow remains an isolated **Sales Copilot Lab**. It preserves the useful example of confirmation-gated writes and auditability, but it is not part of the SmartCS primary product, demo, or first resume bullet.

## Data and Lifecycle Boundary

The first release introduces a narrow support-handoff record with only the data needed for the HR service loop:

- tenant and requesting employee;
- original question;
- reason for handoff;
- source summary or explicit no-source result;
- open, assigned, and resolved lifecycle state;
- timestamps and audit metadata.

This is intentionally not a full ticketing system. There is no SLA engine, notification center, approval flow, external HRIS synchronization, or automatic case resolution in this release.

## FastGPT Boundary

The local FastGPT deployment under D:\DevData\smartcs-fastgpt-poc\ remains a separate, fictional-data proof of concept. It demonstrates that a mature RAG platform and the selected models can be configured locally. It is not a SmartCS runtime dependency and does not replace SmartCS retrieval, identity, authorization, audit, or support-handoff behavior.

No FastGPT adapter, provider credential, container dependency, or workflow UI is added to the SmartCS primary path in this milestone. The PoC may later inform a documented technology-selection decision, but it is not a resume headline.

## Scope and Non-Goals

### In Scope

- Fictional HR policy documents and repeatable local demo data.
- Tenant- and role-scoped HR knowledge retrieval with response-level citations.
- A stateful HR Agent that can select the first-release Skills.
- Confirmation-gated human-support handoff and a minimal lifecycle view.
- Tests for authorization, retrieval evidence, handoff behavior, and ingestion-failure paths.
- A concise demonstration and interview narrative that accurately explains the engineering trade-offs.

### Explicitly Out of Scope

- External-customer service channels, sales CRM expansion, and generic workflow editing.
- A general multi-agent framework, tool marketplace, or autonomous HR decisions.
- Direct integration with Workday, SAP SuccessFactors, Feishu, or another HRIS.
- Leave balance reads, leave submission, contract, payroll, performance, or high-risk personnel decisions.
- Production-SaaS claims, real enterprise data, or public FastGPT administration.

## Future Capability Roadmap

The foundation grows by adding narrowly-defined HR Skills only after a business owner, source system, authorization boundary, confirmation behavior, and audit requirement are specified.

| Later capability | Example future Skill | Required boundary |
| --- | --- | --- |
| Leave information | get_leave_balance | Read-only HRIS adapter scoped to the current employee. |
| Leave submission | draft_leave_request, submit_leave_request | Explicit confirmation, idempotency key, and external approval state. |
| Onboarding help | get_onboarding_task_status | Employee-specific task visibility and source-system mapping. |
| Employment proof | draft_employment_certificate_request | Human review and document-generation audit trail. |

This roadmap is directional, not an implementation commitment for the current two-week milestone.

## Two-Week Delivery Sequence

1. **Primary-path cleanup:** align README, API descriptions, demo, and interview narrative to the HR Agent foundation; keep Sales Copilot isolated.
2. **Grounded HR answer:** make citation presence and no-source behavior explicit in the response contract and tests.
3. **HR Support Skill:** add handoff draft, confirmation-gated creation, minimal lifecycle APIs, admin view, and audit coverage.
4. **Safety regression:** add tenant/role, malformed-import, unsupported-answer, and handoff-lifecycle tests.
5. **Portfolio delivery:** create a reproducible demo command, three-minute Chinese demo script, and role-specific resume/interview bullets.

Each delivery stage ends with a user-visible progress report containing changed behavior, verification evidence, a resume bullet, an interview explanation, and remaining limitations.

## Definition of Done

The milestone is complete only when all of the following are demonstrated with fictional data:

1. An HR administrator can import a policy document and see a clear ingestion result.
2. An authorized employee receives a source-backed answer to a covered question.
3. A vague request can receive an appropriate clarification instead of a guessed policy conclusion.
4. A policy exception or no-source query produces a support-handoff draft, and only explicit confirmation creates the record.
5. The employee can view their own request status and HR can progress the lifecycle.
6. Cross-tenant and unauthorized access to documents, citations, and support requests is denied.
7. Automated tests cover the primary happy path and the key safety failures.
8. A new local environment can follow the runbook and complete the three-minute demonstration without real enterprise data.

## Interview Positioning

SmartCS should be described as an enterprise AI application engineering sample, not as a finished commercial HR product:

> Designed and built a governed HR service Agent foundation with FastAPI, tenant-aware JWT access, source-backed RAG, typed HR Skills, confirmation-gated human handoff, auditability, and regression tests.

The strongest explanation is that the project treats trustworthy delegation as the product: the Agent dynamically chooses an authorized Skill, while the backend retains deterministic control over access, evidence, and writes.
