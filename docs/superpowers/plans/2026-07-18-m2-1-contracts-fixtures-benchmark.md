# M2-1 Document Contracts, Fixtures, and Baseline Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish typed document-ingestion contracts, a committed synthetic HR document corpus, and a repeatable JSON baseline benchmark without changing the current upload API or adding Docling.

**Architecture:** Add small Pydantic contracts beside the existing parsers, keep `parse_file()` and `chunk_text()` behavior unchanged, and benchmark those existing functions against generated non-confidential binary fixtures. The report records current successes and known failures so M2-2 and M2-3 can prove measurable improvement instead of replacing the baseline.

**Tech Stack:** Python 3.12, Pydantic 2, PyMuPDF, python-docx, openpyxl, pytest, existing SmartCS Conda environment.

## Global Constraints

- Do not add Docling, OCR models, LlamaIndex, a queue, a vector database, or any new dependency in M2-1.
- Keep `POST /api/v1/admin/{tenant_slug}/documents/upload`, `parse_file(filename, data) -> str`, and `chunk_text(text) -> list[str]` behavior compatible.
- Use only synthetic HR data in committed fixtures; no user, employer, credential, or production document data.
- Keep generated fixture files small and deterministic; do not write caches or generated artifacts to `C:`.
- Follow strict TDD for production behavior: write one failing test, run it and verify the expected failure, then add the minimum implementation.
- Do not claim high PDF accuracy from the baseline; report corpus-specific facts and failures.

---

### Task 1: Add normalized parsing contracts

**Files:**
- Create: `app/core/parsing/contracts.py`
- Create: `tests/test_parsing_contracts.py`

**Interfaces:**
- Produces: `ParseQuality`, `ParsedElement`, `ParsedDocument`, `KnowledgeChunk`, and `DocumentParser`.
- `ParsedDocument.plain_text` returns non-empty element text joined by double newlines.
- `DocumentParser.parse(filename: str, data: bytes) -> ParsedDocument` is the interface consumed by M2-2 parser routes.

- [ ] **Step 1: Write failing contract tests**

```python
import pytest
from pydantic import ValidationError


def test_parsed_document_preserves_source_structure():
    from app.core.parsing.contracts import ParsedDocument, ParsedElement

    document = ParsedDocument(
        parser_name="fixture",
        parser_version="1",
        page_count=2,
        elements=[
            ParsedElement(
                text="Annual leave policy",
                element_type="heading",
                page_start=1,
                section_path=["Leave"],
            ),
            ParsedElement(
                text="Ten years of service grants ten days.",
                element_type="paragraph",
                page_start=2,
                section_path=["Leave", "Entitlement"],
            ),
        ],
    )

    assert document.plain_text == (
        "Annual leave policy\n\nTen years of service grants ten days."
    )
    assert document.elements[0].page_end == 1
    assert document.elements[1].section_path == ["Leave", "Entitlement"]


def test_parsed_element_rejects_invalid_page_span():
    from app.core.parsing.contracts import ParsedElement

    with pytest.raises(ValidationError, match="page_end"):
        ParsedElement(
            text="policy",
            element_type="paragraph",
            page_start=3,
            page_end=2,
        )


def test_parsed_document_rejects_element_outside_page_count():
    from app.core.parsing.contracts import ParsedDocument, ParsedElement

    with pytest.raises(ValidationError, match="page_count"):
        ParsedDocument(
            parser_name="fixture",
            parser_version="1",
            page_count=1,
            elements=[
                ParsedElement(
                    text="page two",
                    element_type="paragraph",
                    page_start=2,
                )
            ],
        )


def test_knowledge_chunk_keeps_display_and_embedding_content_separate():
    from app.core.parsing.contracts import KnowledgeChunk

    chunk = KnowledgeChunk(
        content="Ten years grants ten days.",
        contextualized_content="Leave > Entitlement\nTen years grants ten days.",
        page_start=2,
        page_end=2,
        section_path=["Leave", "Entitlement"],
        element_types=["table"],
        source_element_indexes=[3],
        token_count=12,
    )

    assert chunk.content != chunk.contextualized_content
    assert chunk.source_element_indexes == [3]
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m pytest tests/test_parsing_contracts.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'app.core.parsing.contracts'`.

- [ ] **Step 3: Implement the minimum contracts**

```python
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator, model_validator

ElementType = Literal["title", "heading", "paragraph", "list", "table", "image"]
QualityStatus = Literal["passed", "review_required", "failed"]
MetadataScalar = str | int | float | bool | None


class ParseQuality(BaseModel):
    status: QualityStatus = "passed"
    metrics: dict[str, int | float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ParsedElement(BaseModel):
    text: str
    element_type: ElementType
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    section_path: list[str] = Field(default_factory=list)
    table_markdown: str | None = None
    metadata: dict[str, MetadataScalar] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def strip_non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must not be empty")
        return value

    @model_validator(mode="after")
    def validate_page_span(self):
        if self.page_start is not None and self.page_end is None:
            self.page_end = self.page_start
        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_end < self.page_start
        ):
            raise ValueError("page_end must be greater than or equal to page_start")
        return self


class ParsedDocument(BaseModel):
    parser_name: str = Field(min_length=1)
    parser_version: str = Field(min_length=1)
    page_count: int = Field(ge=0)
    elements: list[ParsedElement]
    quality: ParseQuality = Field(default_factory=ParseQuality)

    @property
    def plain_text(self) -> str:
        return "\n\n".join(element.text for element in self.elements)

    @model_validator(mode="after")
    def validate_page_bounds(self):
        for element in self.elements:
            if element.page_end is not None and element.page_end > self.page_count:
                raise ValueError("element page span exceeds page_count")
        return self


class KnowledgeChunk(BaseModel):
    content: str = Field(min_length=1)
    contextualized_content: str = Field(min_length=1)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    section_path: list[str] = Field(default_factory=list)
    element_types: list[ElementType] = Field(default_factory=list)
    source_element_indexes: list[int] = Field(default_factory=list)
    token_count: int = Field(ge=0)
    metadata: dict[str, MetadataScalar] = Field(default_factory=dict)


@runtime_checkable
class DocumentParser(Protocol):
    name: str
    version: str

    def supports(self, filename: str) -> bool: ...

    def parse(self, filename: str, data: bytes) -> ParsedDocument: ...
```

- [ ] **Step 4: Run contract tests and existing document tests**

Run:

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m pytest tests/test_parsing_contracts.py tests/test_document_service.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add -- app/core/parsing/contracts.py tests/test_parsing_contracts.py
git commit -m "feat: define structured document contracts"
```

---

### Task 2: Add the synthetic enterprise-document fixture corpus

**Files:**
- Create: `tests/fixtures/documents/generate_fixtures.py`
- Create: `tests/fixtures/documents/manifest.json`
- Generate: `tests/fixtures/documents/clean_policy.pdf`
- Generate: `tests/fixtures/documents/repeated_headers.pdf`
- Generate: `tests/fixtures/documents/leave_table.pdf`
- Generate: `tests/fixtures/documents/scanned_policy.pdf`
- Generate: `tests/fixtures/documents/mixed_policy.pdf`
- Generate: `tests/fixtures/documents/two_column_policy.pdf`
- Generate: `tests/fixtures/documents/encrypted_policy.pdf`
- Generate: `tests/fixtures/documents/headed_policy.docx`
- Generate: `tests/fixtures/documents/hr_contacts.xlsx`
- Create: `tests/test_document_fixtures.py`

**Interfaces:**
- `manifest.json` has `schema_version: 1` and a `fixtures` list.
- Each fixture entry provides `id`, `filename`, `format`, `category`, `expected_baseline_status`, `required_facts`, and optional `expected_page_count`.
- `generate_fixtures.py` regenerates the same small files without network access.

- [ ] **Step 1: Write the failing fixture inventory test**

```python
import json
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "documents"


def test_document_fixture_manifest_covers_enterprise_shapes():
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    entries = manifest["fixtures"]

    assert manifest["schema_version"] == 1
    assert {entry["category"] for entry in entries} == {
        "clean_text",
        "repeated_header_footer",
        "table",
        "scanned",
        "mixed_text_scan",
        "two_column",
        "encrypted",
        "headed_docx",
        "multi_sheet_xlsx",
    }
    assert all((FIXTURE_DIR / entry["filename"]).is_file() for entry in entries)
    assert all(entry["required_facts"] for entry in entries if entry["category"] != "encrypted")
```

- [ ] **Step 2: Run the inventory test and verify RED**

Run:

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m pytest tests/test_document_fixtures.py -q
```

Expected: failure because `manifest.json` does not exist.

- [ ] **Step 3: Add the manifest and deterministic generator**

The generator uses only installed libraries and fixed synthetic content:

```python
from datetime import datetime, timezone
from pathlib import Path

import fitz
from docx import Document
from openpyxl import Workbook

ROOT = Path(__file__).parent


FIXED_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


def add_text(page, point, text, size=11):
    page.insert_text(point, text, fontname="china-s", fontsize=size)


def save_pdf(name, pages):
    document = fitz.open()
    for draw_page in pages:
        page = document.new_page(width=595, height=842)
        draw_page(page)
    document.set_metadata({"title": name, "creationDate": "D:20260101000000Z"})
    document.save(ROOT / name, garbage=4, deflate=True, no_new_id=True)
    document.close()


def build_clean_policy():
    def page_one(page):
        add_text(page, (72, 80), "北辰科技员工年假制度", 16)
        add_text(page, (72, 130), "制度版本：2026.1")

    def page_two(page):
        add_text(page, (72, 80), "年假标准")
        add_text(page, (72, 130), "工龄满十年的员工每年享有十天年假。")

    save_pdf("clean_policy.pdf", [page_one, page_two])


def build_repeated_headers():
    pages = []
    facts = ["年假申请应提前三个工作日提交。", "病假应提供医疗证明。", "婚假应一次性休完。"]
    for index, fact in enumerate(facts, start=1):
        def draw(page, page_number=index, policy_fact=fact):
            add_text(page, (72, 50), "北辰科技人力资源制度")
            add_text(page, (72, 120), policy_fact)
            add_text(page, (250, 810), f"第 {page_number} 页")

        pages.append(draw)
    save_pdf("repeated_headers.pdf", pages)


def build_leave_table():
    def draw(page):
        add_text(page, (72, 70), "年假天数对照表", 16)
        xs = [72, 250, 430]
        ys = [110, 150, 190, 230, 270]
        for x in xs:
            page.draw_line((x, ys[0]), (x, ys[-1]))
        for y in ys:
            page.draw_line((xs[0], y), (xs[-1], y))
        rows = [("工龄", "年假天数"), ("0-9年", "5天"), ("10-19年", "10天"), ("20年以上", "15天")]
        for row_index, row in enumerate(rows):
            add_text(page, (82, 137 + row_index * 40), row[0])
            add_text(page, (270, 137 + row_index * 40), row[1])

    save_pdf("leave_table.pdf", [draw])


def image_only_page(text):
    source = fitz.open()
    page = source.new_page(width=595, height=842)
    add_text(page, (72, 100), text)
    pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
    image = pixmap.tobytes("png")
    source.close()
    return image


def build_scanned_policy():
    image = image_only_page("育儿假每年五天。")
    output = fitz.open()
    image_page = output.new_page(width=595, height=842)
    image_page.insert_image(image_page.rect, stream=image)
    output.save(ROOT / "scanned_policy.pdf", garbage=4, deflate=True, no_new_id=True)
    output.close()


def build_mixed_policy():
    output = fitz.open()
    text_page = output.new_page(width=595, height=842)
    add_text(text_page, (72, 100), "驻外员工住宿由公司统一安排。")
    image_page = output.new_page(width=595, height=842)
    image_page.insert_image(image_page.rect, stream=image_only_page("驻外补贴标准为每月3000元。"))
    output.save(ROOT / "mixed_policy.pdf", garbage=4, deflate=True, no_new_id=True)
    output.close()


def build_two_column_policy():
    def draw(page):
        add_text(page, (72, 70), "入职办理", 15)
        add_text(page, (72, 110), "新员工应在首日完成身份核验。")
        add_text(page, (320, 70), "离职办理", 15)
        add_text(page, (320, 110), "离职员工应在三天内归还设备。")

    save_pdf("two_column_policy.pdf", [draw])


def build_encrypted_policy():
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    add_text(page, (72, 100), "加密制度测试内容。")
    document.save(
        ROOT / "encrypted_policy.pdf",
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="fixture-owner",
        user_pw="fixture-password",
        no_new_id=True,
    )
    document.close()


def build_docx():
    document = Document()
    document.core_properties.created = FIXED_TIME
    document.core_properties.modified = FIXED_TIME
    document.add_heading("员工证明开具制度", level=1)
    document.add_heading("办理时效", level=2)
    document.add_paragraph("在职证明应在两个工作日内开具。")
    document.save(ROOT / "headed_policy.docx")


def build_xlsx():
    workbook = Workbook()
    workbook.properties.created = FIXED_TIME
    workbook.properties.modified = FIXED_TIME
    contacts = workbook.active
    contacts.title = "HR联系人"
    contacts.append(["部门", "联系人"])
    contacts.append(["薪酬福利", "payroll@example.test"])
    offices = workbook.create_sheet("办公地点")
    offices.append(["城市", "HRBP"])
    offices.append(["上海", "测试联系人"])
    workbook.save(ROOT / "hr_contacts.xlsx")


def main():
    build_clean_policy()
    build_repeated_headers()
    build_leave_table()
    build_scanned_policy()
    build_mixed_policy()
    build_two_column_policy()
    build_encrypted_policy()
    build_docx()
    build_xlsx()


if __name__ == "__main__":
    main()
```

`manifest.json` records the exact target facts and current baseline expectations:

```json
{
  "schema_version": 1,
  "fixtures": [
    {"id": "clean-policy", "filename": "clean_policy.pdf", "format": "pdf", "category": "clean_text", "expected_baseline_status": "parsed", "expected_page_count": 2, "required_facts": ["工龄满十年的员工每年享有十天年假。"]},
    {"id": "repeated-headers", "filename": "repeated_headers.pdf", "format": "pdf", "category": "repeated_header_footer", "expected_baseline_status": "parsed", "expected_page_count": 3, "required_facts": ["年假申请应提前三个工作日提交。", "病假应提供医疗证明。", "婚假应一次性休完。"]},
    {"id": "leave-table", "filename": "leave_table.pdf", "format": "pdf", "category": "table", "expected_baseline_status": "parsed", "expected_page_count": 1, "required_facts": ["工龄", "年假天数", "20年以上", "15天"]},
    {"id": "scanned-policy", "filename": "scanned_policy.pdf", "format": "pdf", "category": "scanned", "expected_baseline_status": "error", "expected_page_count": 1, "required_facts": ["育儿假每年五天。"]},
    {"id": "mixed-policy", "filename": "mixed_policy.pdf", "format": "pdf", "category": "mixed_text_scan", "expected_baseline_status": "parsed", "expected_page_count": 2, "required_facts": ["驻外员工住宿由公司统一安排。", "驻外补贴标准为每月3000元。"]},
    {"id": "two-column-policy", "filename": "two_column_policy.pdf", "format": "pdf", "category": "two_column", "expected_baseline_status": "parsed", "expected_page_count": 1, "required_facts": ["新员工应在首日完成身份核验。", "离职员工应在三天内归还设备。"]},
    {"id": "encrypted-policy", "filename": "encrypted_policy.pdf", "format": "pdf", "category": "encrypted", "expected_baseline_status": "error", "expected_page_count": 1, "required_facts": []},
    {"id": "headed-docx", "filename": "headed_policy.docx", "format": "docx", "category": "headed_docx", "expected_baseline_status": "parsed", "required_facts": ["员工证明开具制度", "在职证明应在两个工作日内开具。"]},
    {"id": "multi-sheet-xlsx", "filename": "hr_contacts.xlsx", "format": "xlsx", "category": "multi_sheet_xlsx", "expected_baseline_status": "parsed", "required_facts": ["payroll@example.test", "上海", "测试联系人"]}
  ]
}
```

- [ ] **Step 4: Generate fixtures and run inventory test GREEN**

Run:

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' tests/fixtures/documents/generate_fixtures.py
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m pytest tests/test_document_fixtures.py -q
```

Expected: fixture generation exits 0 and the inventory test passes.

- [ ] **Step 5: Regenerate and verify semantic determinism**

Run the generator a second time, rerun the inventory test, and inspect Git for
unexpected source changes. ZIP and PDF container metadata are not used as an
accuracy signal; fixture facts and structure are the stable contract.

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' tests/fixtures/documents/generate_fixtures.py
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m pytest tests/test_document_fixtures.py -q
git status --short -- tests/fixtures/documents
```

Expected: the inventory test passes and exactly nine generated document files
remain present. The benchmark tests, not binary hashes, verify their stable
semantic content.

- [ ] **Step 6: Commit Task 2**

```powershell
git add -- tests/fixtures/documents tests/test_document_fixtures.py
git commit -m "test: add synthetic HR document corpus"
```

---

### Task 3: Add the repeatable baseline benchmark

**Files:**
- Create: `scripts/benchmark_document_ingestion.py`
- Create: `tests/test_document_benchmark.py`

**Interfaces:**
- `async run_benchmark(fixture_dir: Path) -> dict` reads `manifest.json`, invokes existing `parse_file()` and `chunk_text()`, and returns JSON-safe results.
- Each result records fixture identity, parse status, elapsed milliseconds, page count where available, character count, chunk count, found and missing required facts, fact recall, and a safe error type/message.
- Summary records total, parsed, errors, required facts, found facts, and aggregate fact recall.
- CLI accepts `--fixture-dir` and optional `--output`; without `--output` it prints JSON to stdout.

- [ ] **Step 1: Write failing benchmark tests**

```python
import json
from pathlib import Path

import pytest

from scripts import benchmark_document_ingestion as benchmark

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "documents"


@pytest.mark.asyncio
async def test_baseline_benchmark_records_known_pdf_limits():
    report = await benchmark.run_benchmark(FIXTURE_DIR)
    results = {item["id"]: item for item in report["results"]}

    assert report["schema_version"] == 1
    assert report["summary"]["total"] == 9
    assert results["clean-policy"]["status"] == "parsed"
    assert results["clean-policy"]["fact_recall"] == 1.0
    assert results["scanned-policy"]["status"] == "error"
    assert results["mixed-policy"]["status"] == "parsed"
    assert "驻外补贴标准为每月3000元。" in results["mixed-policy"]["missing_facts"]
    assert results["encrypted-policy"]["status"] == "error"


def test_benchmark_cli_writes_json(tmp_path):
    output = tmp_path / "baseline.json"

    exit_code = benchmark.main(
        ["--fixture-dir", str(FIXTURE_DIR), "--output", str(output)]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["total"] == 9
```

- [ ] **Step 2: Run benchmark tests and verify RED**

Run:

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m pytest tests/test_document_benchmark.py -q
```

Expected: import fails because `scripts.benchmark_document_ingestion` does not exist.

- [ ] **Step 3: Implement the minimum benchmark**

```python
import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Sequence

from app.core.parsing.chunker import chunk_text
from app.core.parsing.parser import parse_file


def _page_count(path: Path) -> int | None:
    if path.suffix.lower() != ".pdf":
        return None
    import fitz

    document = fitz.open(path)
    try:
        return document.page_count
    finally:
        document.close()


async def _benchmark_fixture(fixture_dir: Path, case: dict) -> dict:
    path = fixture_dir / case["filename"]
    started = time.perf_counter()
    base = {
        "id": case["id"],
        "filename": case["filename"],
        "format": case["format"],
        "category": case["category"],
        "expected_baseline_status": case["expected_baseline_status"],
        "page_count": _page_count(path),
    }
    try:
        text = parse_file(path.name, path.read_bytes())
        chunks = await chunk_text(text)
        found = [fact for fact in case["required_facts"] if fact in text]
        missing = [fact for fact in case["required_facts"] if fact not in text]
        required = len(case["required_facts"])
        return {
            **base,
            "status": "parsed",
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "character_count": len(text),
            "chunk_count": len(chunks),
            "found_facts": found,
            "missing_facts": missing,
            "fact_recall": len(found) / required if required else 1.0,
            "error_type": None,
            "error": None,
        }
    except Exception as exc:
        return {
            **base,
            "status": "error",
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "character_count": 0,
            "chunk_count": 0,
            "found_facts": [],
            "missing_facts": case["required_facts"],
            "fact_recall": 0.0,
            "error_type": type(exc).__name__,
            "error": str(exc)[:300],
        }


async def run_benchmark(fixture_dir: Path) -> dict:
    manifest = json.loads((fixture_dir / "manifest.json").read_text(encoding="utf-8"))
    results = [
        await _benchmark_fixture(fixture_dir, case)
        for case in manifest["fixtures"]
    ]
    required = sum(len(case["required_facts"]) for case in manifest["fixtures"])
    found = sum(len(item["found_facts"]) for item in results)
    return {
        "schema_version": 1,
        "benchmark": "smartcs-baseline-parser",
        "results": results,
        "summary": {
            "total": len(results),
            "parsed": sum(item["status"] == "parsed" for item in results),
            "errors": sum(item["status"] == "error" for item in results),
            "required_facts": required,
            "found_facts": found,
            "fact_recall": found / required if required else 1.0,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark SmartCS baseline document ingestion")
    parser.add_argument("--fixture-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = asyncio.run(run_benchmark(args.fixture_dir))
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run benchmark tests GREEN**

Run:

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m pytest tests/test_document_benchmark.py -q
```

Expected: both tests pass without network access.

- [ ] **Step 5: Run the actual baseline and inspect the report**

Run:

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' scripts/benchmark_document_ingestion.py --fixture-dir tests/fixtures/documents --output 'D:\DevData\smartcs\benchmarks\m2-1-baseline.json'
Get-Content 'D:\DevData\smartcs\benchmarks\m2-1-baseline.json'
```

Expected: nine per-fixture results; clean text is parsed, scanned and encrypted PDFs are errors, and the mixed PDF records at least one missing fact. The report contains no credentials or user data.

- [ ] **Step 6: Commit Task 3**

```powershell
git add -- scripts/benchmark_document_ingestion.py tests/test_document_benchmark.py
git commit -m "feat: add document ingestion baseline benchmark"
```

---

### Task 4: Document, verify, review, and close M2-1

**Files:**
- Create: `docs/operations/document-ingestion-benchmark.md`
- Modify: `docs/planning/ROADMAP.md`
- Modify: `docs/superpowers/plans/2026-07-18-m2-1-contracts-fixtures-benchmark.md`

**Interfaces:**
- The runbook gives the exact Conda command and `D:\DevData` output path.
- Roadmap records M2-1 as delivered without marking the whole Milestone 2 complete.

- [ ] **Step 1: Write the benchmark runbook**

The runbook must explain:

```markdown
# Document Ingestion Baseline Benchmark

## Purpose

This command measures the current SmartCS parser against committed synthetic HR documents. It records known failures; it is not a universal PDF-accuracy score.

## Run

```powershell
New-Item -ItemType Directory -Force 'D:\DevData\smartcs\benchmarks' | Out-Null
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' scripts/benchmark_document_ingestion.py --fixture-dir tests/fixtures/documents --output 'D:\DevData\smartcs\benchmarks\m2-1-baseline.json'
```

## Interpretation

- `parsed` means the baseline parser returned text, not that layout is correct.
- `fact_recall` is exact required-fact presence on this synthetic corpus.
- Scanned, mixed, table, and multi-column results define the gaps M2-2 must improve.
- Do not commit local reports or anonymized company documents.
```

- [ ] **Step 2: Run focused verification**

Run:

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m pytest tests/test_parsing_contracts.py tests/test_document_fixtures.py tests/test_document_benchmark.py tests/test_document_service.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run the complete regression suite**

Run:

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m pytest -q
```

Expected: zero failures.

- [ ] **Step 4: Run repository checks**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; only M2-1 files plus the pre-existing untracked `docs/superpowers/plans/2026-07-17-smartcs-hr-agent-foundation.md` appear before the final commit.

- [ ] **Step 5: Request correctness review and address findings**

Review the complete M2-1 diff against:

- typed contract invariants;
- deterministic and non-confidential fixtures;
- offline benchmark behavior;
- current upload compatibility;
- no new dependencies;
- no cache or model data on `C:`.

Fix every critical or important finding with a failing regression test before implementation changes.

- [ ] **Step 6: Update roadmap and commit Task 4**

```powershell
git add -- docs/operations/document-ingestion-benchmark.md docs/planning/ROADMAP.md docs/superpowers/plans/2026-07-18-m2-1-contracts-fixtures-benchmark.md
git commit -m "docs: record M2-1 document baseline"
```

- [ ] **Step 7: Produce the M2-1 checkpoint report and stop**

Report:

- contract and corpus deliverables;
- exact focused/full test counts;
- the baseline report path and measured gaps;
- resume bullet, interview explanation, and demo path;
- commit SHAs and whether they were pushed;
- explicit stop before M2-2 Docling installation.
