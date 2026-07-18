# Document Ingestion Baseline Benchmark

## Purpose

This command measures the current SmartCS parser against committed synthetic HR
documents. It records known failures; it is not a universal PDF-accuracy score
or a claim about production documents. The baseline is a fixed comparison point
for later parser work.

## Run

From the repository root, run:

```powershell
New-Item -ItemType Directory -Force 'D:\DevData\smartcs\benchmarks' | Out-Null
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' scripts/benchmark_document_ingestion.py --fixture-dir tests/fixtures/documents --output 'D:\DevData\smartcs\benchmarks\m2-1-baseline.json'
```

The JSON report stays under `D:\DevData\smartcs\benchmarks`; it is local
generated output and must not be committed.

## Interpretation

- `parsed` means the baseline parser returned text, not that page layout,
  reading order, tables, or source structure are correct.
- `fact_recall` is exact required-fact presence on this synthetic corpus. It is
  not a general accuracy metric.
- The current baseline has 9 fixtures: 7 parsed, 2 errors, 18 required facts,
  and 16 found facts (88.89% aggregate fact recall).
- Scanned PDFs have no text layer and currently error because this baseline has
  no OCR route. Encrypted PDFs also error because no password/unlock flow is
  provided.
- Mixed text-and-scan PDFs may parse their text pages while missing facts on
  image-only pages; this baseline records that partial result rather than
  treating it as complete extraction.
- Table and multi-column fixtures are included as diagnostic shapes. A parsed
  result does not establish preserved table structure or reliable reading order.
- These scanned, encrypted, mixed, table, and multi-column outcomes define the
  gaps M2-2 must improve.

## Data Handling

Run only the committed synthetic fixture corpus. Do not commit local reports,
real enterprise documents, or anonymized company documents.
