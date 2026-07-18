# M2-2 Task 2 Report

## Status

Implemented structured native parsing and deterministic PDF routing signals.
The legacy `parse_file()` API and M2-1 text extraction behavior remain intact.

## Delivered

- Added `ParsedDocument.metadata` with a backward-compatible empty default.
- Added structured TXT/Markdown, DOCX, XLSX, and clean-PDF native parsers.
- Preserved DOCX body order, title/heading paths, Markdown tables, XLSX sheet
  names and row bounds, and native PDF page spans.
- Added controlled PDF decisions for `native`, `advanced`, and `rejected` with
  fixed reasons. Encrypted, zero-page, invalid, sparse, table, and two-column
  PDFs cannot expose raw PyMuPDF errors.
- Added `AdvancedParserRequired` for advanced PDF routes. No Docling code,
  import, installation, or fallback text extraction was added.

## TDD Evidence

- Added the two required test modules before implementation; initial RED run:
  `15 failed` because `app.core.parsing.router` did not exist.
- Added zero-page and invalid-PDF regressions and observed their intentional
  RED failures before restoring the minimal route handling.
- Added DOCX `Title` preservation regression and observed the RED failure
  before mapping it to `element_type="title"`.

## Verification

- `pytest tests/test_structured_native_parser.py tests/test_parser_router.py tests/test_parsing_contracts.py tests/test_document_service.py tests/test_document_benchmark.py -q`
  - `52 passed, 1 warning`
- `pytest -q`
  - `225 passed, 1 warning`
- `git diff --check`
  - clean
- The retained M2-1 benchmark test asserts the baseline remains `16/18`.

## Follow-up Boundary

Advanced routes deliberately stop at `AdvancedParserRequired`; the optional
Docling adapter and production integration are reserved for later tasks.
