# M2-2 Advanced Parsing, Provenance, and Quality Gates Implementation Plan

> **Execution:** Use subagent-driven development task by task. Parallel work is
> limited to read-only research, disjoint new modules, and independent review;
> integration changes remain sequential.

**Goal:** Add a hybrid PDF parser with an optional Docling/Tesseract advanced
route, preserve page/section/table provenance through deterministic chunks and
citations, and prevent incomplete documents from becoming searchable.

**Architecture:** Keep the existing upload API, PyMuPDF clean-PDF fast path,
SQL tenant/role authorization, Chroma IDs, and BM25 IDs. Add a SmartCS-owned
structured parser router and quality gate. Docling is a parser adapter only.
New documents use structured chunks; legacy documents remain searchable with
nullable provenance. A `review_required` or `failed` document is never added to
Chroma or BM25.

**Environment:** Python 3.12 CPU environment at
`D:\2026.07.09\conda-envs\smart-cs`. All downloaded packages, models, and OCR
data must use configured directories under `D:\DevData` before installation.

## Global Constraints

- Quality outranks speed. Do not merge on aggregate scores when any required
  fixture fact, table relation, page span, or tenant/role regression fails.
- Preserve `parse_file(filename, data) -> str` and
  `chunk_text(text) -> list[str]` for legacy callers and the M2-1 baseline.
- Add structured entry points for production ingestion instead of changing the
  old baseline functions in place.
- Keep Docling optional. Clean PDFs, TXT, Markdown, DOCX, and XLSX must work
  without importing Docling.
- Use deterministic OCR configuration: Tesseract CLI, CPU, languages
  `chi_sim` and `eng`. Do not use automatic OCR backend selection.
- Never fall back from a scanned or mixed PDF to incomplete text and mark it
  ready. Advanced-parser absence or low quality produces `review_required` or
  `failed` with a safe public reason.
- Only SQL-loaded `Document` and `DocumentChunk` rows are trusted for tenant,
  role, status, and citation provenance. Chroma metadata is not an
  authorization source.
- Do not add document versioning, original-file storage, reindex generations,
  queues, or LlamaIndex in M2-2; those belong to M2-3/M4.
- Follow TDD for every production behavior: observe the intended failure,
  implement the minimum fix, and re-run the focused test.
- Do not touch the unrelated untracked plan
  `docs/superpowers/plans/2026-07-17-smartcs-hr-agent-foundation.md`.

## Acceptance Matrix

| Fixture | Expected route/result | Required quality evidence |
| --- | --- | --- |
| clean policy PDF | PyMuPDF fast path, `passed` | 1/1 facts, two pages |
| repeated header PDF | routed result, `passed` | 3/3 facts, no fact regression |
| leave table PDF | Docling advanced path, `passed` | 4/4 facts; header and `20年以上 / 15天` remain associated |
| scanned policy PDF | Docling + OCR, `passed` | 1/1 facts, one page, non-empty chunk |
| mixed policy PDF | Docling + OCR, `passed` | 2/2 facts across both pages |
| two-column PDF | Docling advanced path, `passed` | 2/2 facts in correct reading order |
| encrypted PDF | `failed` or `review_required` | never indexed; safe reason |
| headed DOCX | native structured parser, `passed` | heading path and 2/2 facts |
| multi-sheet XLSX | native structured parser, `passed` | sheet metadata and 3/3 facts |

The committed synthetic corpus must reach 18/18 declared-fact recall and
18/18 chunk-fact recall for documents expected to parse. This is a corpus gate,
not a claim of universal PDF or OCR accuracy.

---

### Task 1: Lock D-drive dependency and artifact configuration

**Files:**
- Modify: `app/config.py`
- Modify: `.env.example`
- Create: `requirements-docling.txt`
- Create: `docs/operations/docling-ocr-setup.md`
- Create: `tests/test_document_parser_config.py`

1. Write failing tests for explicit Docling artifact, Hugging Face, Torch, and
   Tesseract paths and CPU/thread settings.
2. Verify RED with:

   ```powershell
   & 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m pytest tests/test_document_parser_config.py -q
   ```

3. Add minimal settings with `D:/DevData/...` defaults and environment
   overrides. Validate that resolved defaults are on `D:` for this supported
   local profile; do not create directories at import time.
4. Add the smallest official Docling PDF/local-model optional dependency. Keep
   it outside base `requirements.txt`.
5. Document an install dry run, model prefetch, Tesseract CLI and `chi_sim`
   verification, and a cache-location audit before the first real parse.
6. Run focused tests and `pip check`; commit.

### Task 2: Add structured native parsers and PDF routing signals

**Files:**
- Create: `app/core/parsing/native_parser.py`
- Create: `app/core/parsing/router.py`
- Modify: `app/core/parsing/contracts.py`
- Modify: `app/core/parsing/parser.py`
- Create: `tests/test_structured_native_parser.py`
- Create: `tests/test_parser_router.py`

1. Write failing tests for structured TXT/MD, headed DOCX, multi-sheet XLSX,
   clean PDF, scanned PDF, mixed PDF, table PDF, two-column PDF, and encrypted
   PDF signals.
2. Add `ParsedDocument.metadata` for controlled parser-route data while keeping
   existing contracts compatible.
3. Implement native parsers that preserve page spans, headings, table Markdown,
   sheet names, row numbers, element types, and source order.
4. Implement deterministic PDF inspection that returns route signals without
   importing Docling. Encrypted, empty, partially empty, table-heavy, and
   multi-column conditions must be explicit.
5. Keep `parse_file()` as a compatibility wrapper over the original behavior;
   expose a new structured router entry point for production.
6. Run focused tests and the M2-1 benchmark to prove the baseline remains
   unchanged; commit.

### Task 3: Implement deterministic quality gates

**Files:**
- Create: `app/core/parsing/quality.py`
- Modify: `app/core/parsing/contracts.py`
- Create: `tests/test_parse_quality_gate.py`

1. Write failing tests for status precedence and metrics: page count, usable
   text pages, empty pages, character count, table count, heading count, OCR
   pages, and elapsed time.
2. Implement hard rules rather than a weighted average:
   - `failed`: parser exception or no usable elements;
   - `review_required`: missing page coverage, incomplete advanced parsing,
     encrypted input, or explicit parser warning that prevents safe indexing;
   - `passed`: all required structural checks pass.
3. Keep benchmark-only declared facts out of production quality decisions.
   Facts are fixture acceptance evidence, not knowledge available at runtime.
4. Ensure warnings and public errors cannot serialize exception messages,
   local paths, credentials, usernames, or environment values.
5. Run focused tests; commit.

### Task 4: Add optional Docling/Tesseract adapter

**Files:**
- Create: `app/core/parsing/docling_parser.py`
- Modify: `app/core/parsing/router.py`
- Create: `tests/test_docling_parser.py`
- Create: `tests/test_advanced_pdf_integration.py`

1. Write failing unit tests using small fake Docling result objects for item
   type mapping, page provenance, headings, table Markdown, OCR page metadata,
   safe failures, and adapter-unavailable behavior.
2. Dynamically import Docling only when the advanced PDF route is selected.
3. Configure PDF layout/table processing and explicit Tesseract CLI OCR with
   `chi_sim` and `eng`, CPU device, configured threads, and D-drive artifacts.
4. Map Docling output into `ParsedDocument` without exposing arbitrary parser
   metadata. Preserve item order and all available page spans.
5. Do not silently switch OCR backends. A missing executable, language pack,
   model artifact, timeout, encrypted file, or incomplete result must become a
   controlled quality outcome.
6. After the optional dependency and artifacts are installed on D:, run real
   fixture integration tests for scanned, mixed, table, and two-column PDFs.
7. Record dependency versions and runtime configuration in test evidence;
   commit.

### Task 5: Add deterministic structural chunking

**Files:**
- Create: `app/core/parsing/structured_chunker.py`
- Create: `tests/test_structured_chunker.py`

1. Write failing tests for page spans, section paths, source element indexes,
   compatible-element merging, table header repetition, and oversized-element
   splitting.
2. Implement `chunk_document(ParsedDocument, title) -> list[KnowledgeChunk]`.
   It must not call the chat model.
3. Preserve headings, list items, tables, page boundaries, and source-element
   lineage. Split oversized content deterministically with the configured token
   counter; repeat table headers for split table chunks.
4. Keep display content separate from contextualized embedding content.
5. Run focused tests and fixture chunk assertions; commit.

### Task 6: Persist provenance and enforce the publication gate

**Files:**
- Modify: `app/models/document.py`
- Create: `migrations/versions/f6a7b8c9d0e1_add_document_parse_provenance.py`
- Modify: `app/services/document_service.py`
- Modify: `app/schemas/document.py`
- Modify: `app/api/admin/document.py`
- Modify: `tests/test_document_service.py`
- Modify: `tests/test_admin_document_api.py`
- Create: `tests/test_document_provenance_migration.py`

1. Write failing model, service, API, and migration tests for parser name/version,
   page count, quality status/details, chunk page span, section path, element
   types, source indexes, and controlled metadata.
2. Add nullable/defaulted columns so legacy rows remain valid. Legacy provenance
   is absent/unknown, never fabricated as `passed`.
3. Make `upload_document()` create a diagnosable document record, call the
   structured parser and chunker, and only index when quality is `passed`.
   Persist inspection chunks as inactive when review is required.
4. Preserve existing chunk IDs and vector/BM25 behavior for ready documents.
   On partial index failure, remove newly created vector/BM25 entries before
   committing the failed status.
5. Expose explicit provenance fields in admin responses. Never return arbitrary
   parser metadata or raw internal exception text.
6. Verify migration upgrade/downgrade on a disposable SQLite database under
   `D:\DevData\smartcs\m2-2`; run focused tests; commit.

### Task 7: Add page-aware citations without weakening authorization

**Files:**
- Modify: `app/core/agent/tools.py`
- Modify: `app/core/agent/hr_agent.py`
- Modify: `app/schemas/hr_support.py`
- Modify: `tests/test_agent_tools.py`
- Modify: `tests/test_assistant_agent.py`
- Modify: `tests/test_security.py`

1. Write failing tests for optional page/section citation fields, legacy chunks,
   review-required exclusion, cross-tenant exclusion, and audience-role
   exclusion.
2. Populate citation provenance only from SQL-loaded rows after tenant, status,
   and role filtering. Keep source IDs and authorization rules unchanged.
3. Extend normalized citation schemas with explicit optional fields only:
   `page_start`, `page_end`, `section_path`, and `element_types`.
4. Verify old sources without provenance still render and no Chroma metadata can
   bypass SQL filtering; commit.

### Task 8: Upgrade the benchmark and run the M2-2 gate

**Files:**
- Modify: `tests/fixtures/documents/manifest.json`
- Modify: `scripts/benchmark_document_ingestion.py`
- Modify: `tests/test_document_benchmark.py`
- Create: `docs/operations/document-ingestion-m2-2.md`
- Modify: `docs/planning/ROADMAP.md`

1. Write failing benchmark tests for expected route, gate status, page/section
   provenance, table association, reading order, 18/18 parsed and chunk facts,
   parser/Docling/OCR versions, and safe errors.
2. Preserve the M2-1 baseline command and expected 16/18 report. Add a distinct
   M2-2 structured benchmark mode/output so improvement remains auditable.
3. Run the M2-2 benchmark with artifacts under D: and record corpus, hardware,
   versions, route decisions, quality status, elapsed time, and limitations.
4. Run focused parsing/document/security tests, then the full suite.
5. Run an independent whole-branch code review. Fix all Critical and Important
   findings and re-run affected tests.
6. Update roadmap and operations documentation only after evidence passes;
   commit and push.

## Final Verification Commands

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m pytest tests/test_parsing_contracts.py tests/test_structured_native_parser.py tests/test_parser_router.py tests/test_parse_quality_gate.py tests/test_docling_parser.py tests/test_advanced_pdf_integration.py tests/test_structured_chunker.py tests/test_document_service.py tests/test_admin_document_api.py tests/test_agent_tools.py tests/test_assistant_agent.py tests/test_security.py tests/test_document_benchmark.py -q

& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m pytest -q

& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' scripts\benchmark_document_ingestion.py --fixture-dir tests\fixtures\documents --output 'D:\DevData\smartcs\benchmarks\m2-1-baseline-after-m2-2.json' --environment-label local-cpu

& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' scripts\benchmark_document_ingestion.py --mode structured --fixture-dir tests\fixtures\documents --output 'D:\DevData\smartcs\benchmarks\m2-2-structured.json' --environment-label local-cpu

git diff --check
```

## Stage Report Deliverables

- Evidence-backed before/after corpus metrics and runtime characteristics.
- A resume bullet naming parser routing, OCR, provenance, and quality gates.
- An interview explanation centered on preventing incomplete HR policy answers.
- A demo path: upload clean/scanned/table PDFs, inspect route and quality,
  retrieve an answer with page-aware citation, and show an encrypted/low-quality
  document excluded from employee search.
- Explicit limitations: synthetic corpus, CPU OCR variance, no version/reindex
  lifecycle until M2-3, and no production claim before M4.
