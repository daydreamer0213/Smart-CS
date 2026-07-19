# SmartCS Document Intelligence and Knowledge Governance Design

**Date:** 2026-07-18

**Status:** Approved; M2-1 delivered, M2-2 authorized on 2026-07-18

## Goal

Upgrade SmartCS from a basic file-to-vector import path into a measurable HR
knowledge ingestion and governance subsystem. The subsystem must turn common,
messy enterprise documents into authorized, traceable, versioned knowledge
chunks without replacing the existing FastAPI, SQLAlchemy, ChromaDB, BM25, or
HR Agent boundaries.

This milestone improves the trustworthiness of policy answers. It does not try
to build a complete HRIS or a generic enterprise data platform.

## Current Baseline

The existing path is functional for clean, text-layer documents:

```text
upload -> parse to plain text -> split -> embed -> SQL + ChromaDB + BM25
```

It already provides tenant-scoped hash deduplication, document-level audience
roles, processing status, embedding retries, index deletion, and admin chunk
inspection.

The current PDF path uses PyMuPDF `page.get_text()` and joins every page into a
single string. The current chunker splits Markdown headings or blank-line
paragraphs, asks the configured LLM to split oversized blocks, and falls back
to an 800-character recursive splitter with 100-character overlap.

The verified limitations are:

- no OCR or scanned-PDF route;
- no layout, reading-order, table, image, header, or footer representation;
- no page number, section path, bounding box, element type, or parser metadata;
- character limits and `len(content) // 4` estimates instead of tokenizer-aware
  limits;
- model-dependent semantic splitting without a stored splitter version;
- no original-file storage for deterministic reprocessing;
- no document version, effective period, source owner, review, or publication
  lifecycle;
- no PDF, DOCX, or XLSX binary fixtures and no parsing-quality benchmark;
- no ingestion lineage connecting source file, parser, chunker, embedding model,
  and resulting index entries.

Therefore, "PDF supported" currently means clean text extraction works. It
does not mean complex enterprise PDFs are recognized accurately.

## Chosen Approach

Use a hybrid parser architecture and keep SmartCS ownership of governance,
authorization, storage, and retrieval.

1. Keep PyMuPDF as the fast path for clean born-digital PDFs.
2. Add Docling as an optional advanced path for scanned, table-heavy,
   multi-column, or low-confidence PDFs.
3. Normalize both paths into a small SmartCS-owned document contract.
4. Chunk deterministically from document structure and embedding-model token
   limits. Do not call the chat model during routine chunking.
5. Preserve the existing ChromaDB + BM25 retrieval and database authorization
   boundary.
6. Use LlamaIndex ingestion and node-parser designs as references only. Do not
   add the full framework unless a benchmark later proves a missing capability
   is cheaper to adopt than maintain locally.

This gives the project advanced parsing where it matters without creating a
second Agent, retriever, vector-store, or authorization architecture.

## Alternatives Rejected

### Only Extend PyMuPDF

This is the smallest dependency change but would require SmartCS to own OCR,
reading-order repair, table reconstruction, and layout heuristics. That is not
a good use of project scope.

### Replace Ingestion and Retrieval with LlamaIndex

LlamaIndex provides useful transformations, caching, semantic splitters, and
hierarchical nodes. A full migration would duplicate the existing LangGraph,
SQLAlchemy, ChromaDB, BM25, and role-filtering boundaries. It also does not by
itself solve PDF OCR and layout recognition.

### Send Every PDF to a Vision Model

This raises cost, latency, privacy, and reproducibility problems. It remains a
future fallback for measured hard cases, not the default parser.

## Normalized Document Contract

Parsers return structured data instead of a single string:

```text
ParsedDocument
  parser_name
  parser_version
  page_count
  quality
  elements[]

ParsedElement
  text
  element_type       # title, heading, paragraph, list, table
  page_start/page_end
  section_path[]
  table_markdown?     # only for tables
  metadata{}

KnowledgeChunk
  content
  contextualized_content
  page_start/page_end
  section_path[]
  element_types[]
  token_count
  metadata{}
```

`content` is displayed and cited. `contextualized_content` adds the document
title and section path for embedding when useful. Security metadata is never
accepted from parser output; tenant and audience values continue to come from
the authenticated upload request and database.

## Parser Routing

The upload endpoint keeps its current contract. An internal router chooses:

- text, Markdown, DOCX, and XLSX: existing deterministic parsers, upgraded to
  return structured elements;
- clean PDF: PyMuPDF fast path when usable text coverage and reading-order
  checks pass;
- empty, low-coverage, scanned, table-heavy, or structurally complex PDF:
  Docling advanced path with OCR and table extraction;
- encrypted, malformed, timed-out, or persistently low-quality files: failed
  or review-required status with a safe reason.

Parser routing decisions and quality signals are stored for diagnosis. A file
must never be marked ready merely because the parser returned some text.

## Chunking Strategy

Chunking follows these rules in order:

1. Preserve headings, list items, table rows, and section boundaries.
2. Merge adjacent small elements only when they share a section and compatible
   element type.
3. Split oversized elements by the configured embedding tokenizer limit.
4. Repeat the section path and table header where needed for local context.
5. Preserve page spans and source element references on every chunk.
6. Use a deterministic fallback for malformed structure.

The first implementation does not add parent-child retrieval, semantic
splitters, rerankers, or contextual retrieval. Those are benchmark-driven
follow-ups, not prerequisites for a reliable baseline.

## Governance Model

The minimal governance fields are:

- source type and source reference;
- original filename and immutable content hash;
- document family and version;
- effective date and optional expiry date;
- owner and review status;
- audience roles and tenant boundary;
- parser, chunker, and embedding versions;
- quality status and quality details;
- original-file storage URI;
- current publication/index generation.

Only the active, approved version is searchable by employees. Reprocessing
creates a new index generation and switches visibility only after all chunks
and indexes succeed. Failed reprocessing must leave the last good generation
available.

Original files and generated parser artifacts are stored through a configured
storage path. Local development defaults to project-local data on `D:`; large
Docling and model caches use a configured path under
`D:\DevData\smartcs`, not the system drive.

## Quality Gates

Each imported document records observable checks:

- detected page count and pages with usable text;
- extracted character and token counts;
- OCR/layout confidence when the parser provides it;
- repeated-header/footer ratio;
- empty or suspiciously short pages;
- table and heading counts;
- parser warnings and elapsed time.

Initial publication decisions use explicit deterministic thresholds and parser
errors. Low-confidence files enter `review_required`; they are not silently
published. The admin API exposes parsed elements, chunks, metadata, warnings,
and the reason for the routing decision.

## Evaluation Corpus

Stage 1 creates small synthetic, non-confidential fixtures covering:

1. clean multi-page Chinese policy PDF;
2. repeated headers and footers;
3. leave-entitlement table;
4. image-only scanned page;
5. mixed text and scanned pages;
6. two-column content;
7. malformed or encrypted PDF;
8. headed DOCX and multi-sheet XLSX.

Later acceptance adds three to five anonymized HR documents supplied by the
user. They remain local and must not be committed.

The benchmark records:

- required facts and their expected pages/sections;
- table rows that must remain associated with headers;
- expected parser route and publication status;
- golden HR questions with expected source chunks.

## Acceptance Criteria

- Every committed fixture has deterministic parser and chunk assertions.
- Scanned or malformed PDFs never become silently ready with missing content.
- Every searchable chunk contains page span, section path when available,
  parser version, chunker version, and index generation.
- Table chunks retain their header context.
- Employee citations include page information when the source provides it.
- Golden-query retrieval Recall@3 is at least 90 percent and no tenant or
  audience-role regression occurs.
- Reprocessing failure leaves the last approved index generation searchable.
- The full existing pytest suite remains green.
- Large parser/model artifacts are verified outside `C:`.

The first benchmark report is a baseline, not a claim of universal PDF
accuracy. Accuracy claims must name the corpus, metric, parser configuration,
and hardware.

## Delivery Phases

### Stage 0: Baseline and Design

Record the current limitations, architecture choice, acceptance corpus, risks,
and phase gates. No dependency or production-code change.

### Stage 1: Contracts and Fixtures

Add normalized document/chunk types, parser interfaces, representative binary
fixtures, baseline tests, and a benchmark command. Preserve the current upload
API and retrieval behavior.

### Stage 2: Advanced PDF Route

Benchmark Docling on the fixture corpus, configure all model artifacts on
`D:`, then add automatic routing and OCR/table extraction. Keep Docling an
optional document-processing dependency rather than a project-wide framework.

For the approved Windows CPU implementation, use Tesseract CLI with explicit
`chi_sim` and `eng` languages as the default OCR backend. Keep OCR backend
selection deterministic: do not use Docling's automatic OCR selection and do
not silently switch backends after a failure. Store pip, Hugging Face, Torch,
Docling, and Tesseract artifacts under configured `D:\DevData` paths before
installing or downloading dependencies.

### Stage 3: Metadata and Structural Chunking

Persist page, section, table, parser, token, and index metadata. Replace chat
model chunking with deterministic, tokenizer-aware structure chunking and add
page-aware citations.

### Stage 4: Governance Lifecycle

Add original-file storage, version/effective-date fields, review status,
atomic reindex generations, quality inspection, and failure-safe rollback to
the last approved generation.

**Delivered 2026-07-19:** SmartCS now retains content-addressed originals on
`D:`, publishes only explicitly approved current snapshots through the SQL
authorization boundary, and builds immutable reindex generations. Parse,
quality, embedding, vector, BM25, integrity, and concurrent-publication
failures leave the last published generation available.

### Stage 5: Evaluation and Delivery

Run parsing and retrieval benchmarks, document results and limitations, update
the demo, and produce resume/interview explanations. Only benchmark-supported
advanced retrieval improvements are considered here.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Docling/OCR dependencies and model artifacts are large | Install only after Stage 1 approval; configure artifact and cache paths on `D:`. |
| CPU parsing is slow on Windows | Benchmark before integration; keep PyMuPDF fast path and record processing time. |
| Chinese OCR and tables vary by document quality | Use a mixed fixture corpus, explicit quality gates, and manual review status. |
| Schema changes invalidate existing vectors | Add an index generation and a controlled reprocessing command; do not mutate old good data in place. |
| Framework overlap obscures project ownership | Keep SmartCS contracts and retrieval; use Docling as a parser component only. |
| Accuracy claims become marketing language | Publish corpus-specific metrics and failure cases, not an unsupported universal percentage. |

## Non-Goals

- No complete HRIS, payroll, attendance, recruitment, or performance system.
- No generic enterprise data middle platform.
- No full LlamaIndex migration.
- No Milvus, distributed workflow engine, or new reranker without benchmark
  evidence.
- No confidential enterprise documents in Git.
- No production claim before real identity, storage, queueing, observability,
  backup, and security controls are added and operated.

## Project-Level Continuation

This design is Milestone 2 of the durable SmartCS roadmap. Completion does not
end the project plan:

1. Milestone 3 integrates one real HR/OA provider for leave balance, employee
   ticket status, confirmation-gated leave drafts, and organization/HR contact
   queries. It integrates with an existing system instead of rebuilding HRIS.
2. Milestone 4 adds durable asynchronous ingestion, retry and reindex recovery,
   audit and observability, notification and SLA controls, enterprise identity,
   and deployment hardening.

Provider selection, credentials, and enterprise identity platform are confirmed
just before those milestones. They are not needed to complete the current
document-governance milestone.

## Resume, Interview, and Demo Outcome

When all stages are complete, the defensible resume bullet is:

> Designed and implemented a governed HR document-ingestion pipeline with
> parser routing, OCR and table-aware extraction, page-level lineage,
> tokenizer-aware structural chunking, versioned indexing, quality gates, and
> corpus-based RAG evaluation while preserving multi-tenant access controls.

The demo will upload clean, scanned, and table-heavy HR documents; show parser
routing and quality status; retrieve a policy answer with page-aware evidence;
reject or hold a low-quality document for review; and prove that a failed
reindex leaves the last approved version available.
