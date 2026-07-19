# M2-2 Document Ingestion

M2-2 keeps the M2-1 baseline benchmark intact and adds a separate structured
benchmark that exercises `parse_structured_file` and `chunk_document`. The
structured report is an acceptance artifact for the committed synthetic HR
corpus, not a general parser accuracy claim.

## Install

Use the supported Python environment at
`D:\2026.07.09\conda-envs\smart-cs\python.exe`. Follow
[`docling-ocr-setup.md`](docling-ocr-setup.md) to install the optional Docling
and Tesseract dependencies and verify `chi_sim` plus `eng`.

Keep all parser data under `D:\DevData\smartcs`. In particular, the configured
temporary directory, Docling artifacts, Hugging Face cache, Torch cache,
Tesseract executable, and tessdata must resolve to the paths defined by app
config. Application startup and the structured benchmark both apply the same
configured cache and temporary paths before parsing; operators do not need to
set `TEMP` or `TMP` manually. Benchmark JSON belongs in
`D:\DevData\smartcs\benchmarks` and must not be committed.

## Run

Run both commands from the repository root in PowerShell. Omitting `--mode`
continues to select the M2-1 baseline parser and chunker.

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' scripts\benchmark_document_ingestion.py `
    --fixture-dir tests\fixtures\documents `
    --output 'D:\DevData\smartcs\benchmarks\m2-1-baseline-after-m2-2.json' `
    --environment-label local-cpu

& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' scripts\benchmark_document_ingestion.py `
    --mode structured `
    --fixture-dir tests\fixtures\documents `
    --output 'D:\DevData\smartcs\benchmarks\m2-2-structured.json' `
    --environment-label local-cpu
```

The structured command may write Docling progress and Tesseract orientation
warnings to the console for sparse synthetic pages. Judge publication safety
from the JSON quality and acceptance gates, not from console silence. It writes
the report first and returns a non-zero exit code when the structured acceptance
gate fails; baseline mode retains its historical zero exit behavior.

## Observe

Inspect the summaries first:

```powershell
$baseline = Get-Content -Raw 'D:\DevData\smartcs\benchmarks\m2-1-baseline-after-m2-2.json' | ConvertFrom-Json
$structured = Get-Content -Raw 'D:\DevData\smartcs\benchmarks\m2-2-structured.json' | ConvertFrom-Json
$baseline.summary
$structured.summary
$structured.results | Select-Object id, status, route, route_reason, indexable, elapsed_ms
```

The M2-2 gate passes only when corpus, parsed-fact, chunk-fact, provenance, and
overall acceptance gates are all `passed`. The corpus gate binds the report to
the committed nine fixture IDs and 18 required facts. Each fixture records:

- route and controlled route reason;
- parser and chunker names and versions;
- quality status, warnings, and metrics;
- element and chunk page spans, section paths, element types, and source indexes;
- per-fact element/chunk evidence, table associations, reading-order checks,
  indexing eligibility, and elapsed time;
- Python, package, Docling, Tesseract, CPU, platform, manifest hash, and git
  context without local paths, usernames, credentials, or raw exception text.

The encrypted fixture must remain `blocked`, `indexable: false`, contain no
chunks, and report exactly `encrypted_input` plus `missing_page_coverage` as its
quality warnings. Any undeclared extra warning fails fixture acceptance.
Unexpected parser exceptions use the fixed public message
`Document processing failed.`

## Verified Evidence

Verified 2026-07-19 on Windows 10 AMD64 with an Intel64 Family 6 Model 158 CPU
and 6 logical CPUs:

- M2-1 baseline: 9 fixtures, 7 parsed, 2 errors, 16/18 facts (88.89%); summed
  fixture elapsed time 0.57 seconds.
- M2-2 structured: 8 parsed, 1 encrypted fixture blocked, 18/18 parsed facts,
  18/18 chunk facts, and all provenance/acceptance gates passed; summed fixture
  elapsed time 16.15 seconds.
- Manifest SHA-256:
  `68ccf288d79b83803b8c87162f21880f45095c40557b22223e9c035b0c734869`.
- Python 3.12.13, PyMuPDF 1.27.2.3, python-docx 1.2.0, openpyxl 3.1.5,
  docling-slim 2.113.0, and Tesseract 5.5.2 with `chi_sim` and `eng`.
- The leave table preserves both header association (`工龄` with `年假天数`)
  and row association (`20年以上` with `15天`) in one table element and chunk,
  with the passing chunk source lineage pointing to the passing table element.
- The two-column fixture preserves declared reading order. Page and section
  provenance passes for PDFs, headed DOCX, and multi-sheet XLSX source lineage.

## Demo Path

Upload the clean, scanned, table, and encrypted fixtures through the admin
document API. Inspect parser route, quality status, and page/section provenance;
retrieve a passed policy with its page-aware citation; then show that the
encrypted document has no searchable chunks and is excluded from employee
knowledge search.

The employee-answering value is completeness: a mixed or scanned HR policy is
not silently published from partial machine text, so an answer cannot omit the
OCR-only allowance while appearing authoritative.

## Limitations

- The nine-document corpus is synthetic. Its 18/18 result is a deterministic
  corpus gate, not production or universal OCR accuracy.
- CPU OCR latency and recognition can vary by hardware, Tesseract build, thread
  scheduling, and sparse-page orientation detection. Re-run the local gate
  after dependency or hardware changes.
- M2-2 has no document version or reindex lifecycle. Those remain later M2-3
  and M2-4 work.
- Chroma and BM25 are separate external indexes. Cleanup is best effort after a
  partial indexing failure; cleanup failure can leave an orphan that is not
  retrievable through trusted SQL rows. M2-4 must add retry and reconciliation.
- No production-readiness claim is made before Milestone 4 reliability,
  observability, deployment, and recovery work is complete.
