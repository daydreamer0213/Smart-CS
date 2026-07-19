import getpass
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from app.core.parsing.contracts import ParseQuality, ParsedDocument, ParsedElement
from scripts import benchmark_document_ingestion as benchmark

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "documents"


def load_manifest():
    return json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))


def fake_structured_parser(*, omit_fact=None, error=None):
    cases = {case["filename"]: case for case in load_manifest()["fixtures"]}

    def parse(filename, _data):
        if error is not None:
            raise error
        case = cases[filename]
        if case["expected_structured_status"] == "blocked":
            return ParsedDocument(
                parser_name="pdf-router",
                parser_version="1",
                page_count=case.get("expected_page_count", 0),
                elements=[],
                quality=ParseQuality(
                    status="failed", warnings=case["expected_quality_warnings"]
                ),
                metadata={
                    "route": case["expected_route"],
                    "route_reason": case["expected_route_reason"],
                },
            )

        elements = []
        associations = case["expected_table_associations"]
        associated_facts = {fact for group in associations for fact in group}
        if associated_facts:
            provenance = case["expected_fact_provenance"][0]
            table_text = " | ".join(case["required_facts"])
            elements.append(
                ParsedElement(
                    text=table_text,
                    table_markdown=table_text,
                    element_type="table",
                    page_start=provenance["page_start"],
                    page_end=provenance["page_end"],
                    section_path=provenance["section_path"],
                )
            )
        for provenance in case["expected_fact_provenance"]:
            fact = provenance["fact"]
            if fact == omit_fact or fact in associated_facts:
                continue
            elements.append(
                ParsedElement(
                    text=fact,
                    element_type="paragraph",
                    page_start=provenance["page_start"],
                    page_end=provenance["page_end"],
                    section_path=provenance["section_path"],
                    metadata=provenance.get("metadata", {}),
                )
            )
        covered_pages = {
            element.page_start for element in elements if element.page_start is not None
        }
        for page in range(1, case.get("expected_page_count", 0) + 1):
            if page not in covered_pages:
                elements.append(
                    ParsedElement(
                        text=f"Supporting text for page {page}.",
                        element_type="paragraph",
                        page_start=page,
                        page_end=page,
                    )
                )
        elements.sort(key=lambda item: item.page_start or 0)
        return ParsedDocument(
            parser_name="docling" if case["expected_route"] == "advanced" else "native-test",
            parser_version="test-version",
            page_count=case.get("expected_page_count", 0),
            elements=elements,
            metadata={
                "route": case["expected_route"],
                "route_reason": case["expected_route_reason"],
            },
        )

    return parse


def test_manifest_declares_structured_acceptance_expectations():
    cases = load_manifest()["fixtures"]
    expected_fields = {
        "expected_structured_status",
        "expected_route",
        "expected_route_reason",
        "expected_quality_status",
        "expected_quality_warnings",
        "expected_indexable",
        "expected_fact_provenance",
        "expected_fact_order",
        "expected_table_associations",
    }

    assert len(cases) == 9
    assert sum(len(case["required_facts"]) for case in cases) == 18
    for case in cases:
        assert expected_fields <= case.keys()
        assert [item["fact"] for item in case["expected_fact_provenance"]] == case["required_facts"]
    leave_table = next(case for case in cases if case["id"] == "leave-table")
    assert {
        tuple(item["section_path"])
        for item in leave_table["expected_fact_provenance"]
    } == {("年 假 天 数 对 照 表",)}


@pytest.mark.asyncio
async def test_structured_benchmark_records_routes_provenance_and_18_fact_gates(monkeypatch):
    monkeypatch.setattr(
        benchmark, "parse_structured_file", fake_structured_parser()
    )

    report = await benchmark.run_structured_benchmark(FIXTURE_DIR, "local-cpu")
    results = {item["id"]: item for item in report["results"]}

    assert report["schema_version"] == 2
    assert report["benchmark"] == "smartcs-structured-parser"
    assert report["mode"] == "structured"
    context = report["run_context"]
    assert set(context["hardware"]) == {"machine", "processor", "logical_cpu_count"}
    assert context["packages"]["docling-slim"]
    assert context["ocr"]["engine"] == "tesseract-cli"
    assert context["ocr"]["languages"] == ["chi_sim", "eng"]
    assert context["structured_chunking"] == {
        "chunker": "smartcs-structured",
        "version": "1",
        "max_tokens": 800,
    }
    assert report["summary"] == {
        "total": 9,
        "parsed": 8,
        "blocked": 1,
        "errors": 0,
        "required_facts": 18,
        "found_facts": 18,
        "chunk_found_facts": 18,
        "fact_recall": 1.0,
        "chunk_fact_recall": 1.0,
        "parsed_fact_gate": "passed",
        "chunk_fact_gate": "passed",
        "provenance_gate": "passed",
        "acceptance_gate": "passed",
    }
    assert results["leave-table"]["table_associations"][1] == {
        "facts": ["20年以上", "15天"],
        "element_indexes": [0],
        "chunk_indexes": [0],
        "passed": True,
    }
    assert results["two-column-policy"]["reading_order"]["passed"] is True
    assert results["clean-policy"]["fact_evidence"][0]["elements"] == [
        {
            "index": 1,
            "element_type": "paragraph",
            "page_start": 2,
            "page_end": 2,
            "section_path": [],
            "metadata": {},
        }
    ]
    docx_evidence = results["headed-docx"]["fact_evidence"][1]
    assert docx_evidence["chunks"][0]["section_path"] == ["员工证明开具制度", "办理时效"]
    xlsx_evidence = results["multi-sheet-xlsx"]["fact_evidence"][0]
    assert xlsx_evidence["elements"][0]["metadata"] == {"sheet_name": "HR联系人"}
    encrypted = results["encrypted-policy"]
    assert encrypted["status"] == "blocked"
    assert encrypted["indexable"] is False
    assert encrypted["route_reason"] == "encrypted"
    assert encrypted["quality"]["warnings"] == ["encrypted_input", "missing_page_coverage"]
    assert encrypted["chunks"] == []
    assert encrypted["safe_reason"] == "Document is not eligible for indexing."
    parsed = results["clean-policy"]
    assert parsed["parser"] == {"name": "native-test", "version": "test-version"}
    assert parsed["chunker"] == {"name": "smartcs-structured", "version": "1"}
    assert parsed["elapsed_ms"] >= parsed["parse_elapsed_ms"] >= 0
    assert parsed["elapsed_ms"] >= parsed["chunk_elapsed_ms"] >= 0


@pytest.mark.asyncio
async def test_structured_summary_gate_fails_when_a_fact_or_provenance_is_missing(monkeypatch):
    monkeypatch.setattr(
        benchmark,
        "parse_structured_file",
        fake_structured_parser(omit_fact="驻外补贴标准为每月3000元。"),
    )

    report = await benchmark.run_structured_benchmark(FIXTURE_DIR)

    assert report["summary"]["found_facts"] == 17
    assert report["summary"]["chunk_found_facts"] == 17
    assert report["summary"]["parsed_fact_gate"] == "failed"
    assert report["summary"]["chunk_fact_gate"] == "failed"
    assert report["summary"]["provenance_gate"] == "failed"
    assert report["summary"]["acceptance_gate"] == "failed"


def test_table_association_requires_facts_in_the_same_row():
    table = "\n".join(
        [
            "| 工龄 | 年假天数 |",
            "| --- | --- |",
            "| 20年以上 | 10天 |",
            "| 10年以上 | 15天 |",
        ]
    )
    element = ParsedElement(
        text=table,
        table_markdown=table,
        element_type="table",
        page_start=1,
    )
    document = ParsedDocument(
        parser_name="test",
        parser_version="1",
        page_count=1,
        elements=[element],
    )
    chunks = benchmark.chunk_document(document, "Leave")

    association = benchmark._table_association(
        ["20年以上", "15天"], document.elements, chunks
    )

    assert association["element_indexes"] == []
    assert association["chunk_indexes"] == []
    assert association["passed"] is False


@pytest.mark.asyncio
async def test_structured_benchmark_uses_safe_errors(monkeypatch):
    secret = "credential=D:/private/parser-model"
    monkeypatch.setattr(
        benchmark,
        "parse_structured_file",
        fake_structured_parser(error=RuntimeError(secret)),
    )
    case = load_manifest()["fixtures"][0]

    result = await benchmark._benchmark_structured_fixture(FIXTURE_DIR, case)

    assert result["status"] == "error"
    assert result["error_type"] == "RuntimeError"
    assert result["error"] == benchmark.SAFE_ERROR_MESSAGE
    assert secret not in json.dumps(result)


@pytest.mark.asyncio
async def test_structured_benchmark_rejects_malformed_expectations_and_continues(
    tmp_path, monkeypatch
):
    valid_case = next(
        case for case in load_manifest()["fixtures"] if case["id"] == "clean-policy"
    )
    invalid_case = {**valid_case, "expected_fact_provenance": "not-a-list"}
    shutil.copy2(FIXTURE_DIR / valid_case["filename"], tmp_path / valid_case["filename"])
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {"schema_version": 1, "fixtures": [invalid_case, valid_case]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        benchmark, "parse_structured_file", fake_structured_parser()
    )

    report = await benchmark.run_structured_benchmark(tmp_path)

    assert report["results"][0]["status"] == "error"
    assert report["results"][0]["error_type"] == "ManifestValidationError"
    assert report["results"][0]["error"] == benchmark.SAFE_ERROR_MESSAGE
    assert report["results"][1]["id"] == "clean-policy"
    assert report["results"][1]["status"] == "parsed"


@pytest.mark.asyncio
async def test_baseline_benchmark_records_known_pdf_limits():
    report = await benchmark.run_benchmark(FIXTURE_DIR)
    results = report["results"]
    cases = load_manifest()["fixtures"]

    assert report["schema_version"] == 1
    assert report["summary"] == {
        "total": 9,
        "parsed": 7,
        "errors": 2,
        "required_facts": 18,
        "found_facts": 16,
        "fact_recall": 16 / 18,
    }
    assert len(results) == len(cases) == 9

    for case, result in zip(cases, results, strict=True):
        expected_found = [
            fact
            for fact in case["required_facts"]
            if fact not in case["expected_missing_facts"]
        ]
        assert result["id"] == case["id"]
        assert result["status"] == case["expected_baseline_status"]
        assert result["found_facts"] == expected_found
        assert result["missing_facts"] == case["expected_missing_facts"]
        assert result["chunk_count"] == case["expected_chunk_count"]

        if result["status"] == "parsed":
            assert result["chunk_found_facts"] == expected_found
            assert result["chunk_missing_facts"] == case["expected_missing_facts"]
            assert result["error_type"] is None
            assert result["error"] is None
        else:
            assert result["chunk_count"] == 0
            assert result["chunk_found_facts"] == []
            assert result["chunk_missing_facts"] == case["required_facts"]
            assert result["error_type"] == "ValueError"
            assert result["error"] == benchmark.SAFE_ERROR_MESSAGE


@pytest.mark.asyncio
async def test_leave_table_keeps_20_years_and_15_days_in_one_chunk():
    path = FIXTURE_DIR / "leave_table.pdf"
    text = benchmark.parse_file(path.name, path.read_bytes())
    chunks = await benchmark.chunk_text(text)

    assert any("20年以上" in chunk and "15天" in chunk for chunk in chunks)


@pytest.mark.asyncio
async def test_benchmark_uses_a_safe_error_message(monkeypatch):
    secret = "token=do-not-serialize-this"

    def fail_parse_file(filename, data):
        raise RuntimeError(secret)

    monkeypatch.setattr(benchmark, "parse_file", fail_parse_file)
    result = await benchmark._benchmark_fixture(
        FIXTURE_DIR,
        {
            "id": "sensitive-error",
            "filename": "clean_policy.pdf",
            "format": "pdf",
            "category": "test",
            "expected_baseline_status": "error",
            "required_facts": [],
        },
    )

    assert result["error_type"] == "RuntimeError"
    assert result["error"] == "Document processing failed."
    assert secret not in json.dumps(result)


@pytest.mark.asyncio
async def test_benchmark_continues_after_page_count_error(monkeypatch):
    original_page_count = benchmark._page_count

    def fail_one_page_count(path):
        if path.name == "clean_policy.pdf":
            raise RuntimeError("private page-count detail")
        return original_page_count(path)

    monkeypatch.setattr(benchmark, "_page_count", fail_one_page_count)
    report = await benchmark.run_benchmark(FIXTURE_DIR)
    results = {item["id"]: item for item in report["results"]}

    assert report["summary"]["total"] == 9
    assert results["clean-policy"]["status"] == "error"
    assert results["clean-policy"]["page_count"] is None
    assert results["headed-docx"]["status"] == "parsed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_case",
    [
        {"id": "missing-fields"},
        {
            "id": 123,
            "filename": "clean_policy.pdf",
            "format": "pdf",
            "category": "clean_text",
            "expected_baseline_status": "parsed",
            "expected_missing_facts": [],
            "expected_chunk_count": 2,
            "required_facts": [],
        },
    ],
    ids=["missing-field", "wrong-type"],
)
async def test_benchmark_continues_after_malformed_manifest_entry(tmp_path, bad_case):
    shutil.copy2(FIXTURE_DIR / "clean_policy.pdf", tmp_path / "clean_policy.pdf")
    valid_case = next(
        case for case in load_manifest()["fixtures"] if case["id"] == "clean-policy"
    )
    manifest = {
        "schema_version": 1,
        "fixtures": [
            bad_case,
            valid_case,
        ],
    }
    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )

    report = await benchmark.run_benchmark(tmp_path)

    assert len(report["results"]) == 2
    assert report["results"][0] == {
        "id": "invalid-manifest-entry-1",
        "filename": None,
        "format": None,
        "category": None,
        "expected_baseline_status": None,
        "page_count": None,
        "status": "error",
        "elapsed_ms": 0.0,
        "character_count": 0,
        "chunk_count": 0,
        "found_facts": [],
        "missing_facts": [],
        "fact_recall": 0.0,
        "chunk_found_facts": [],
        "chunk_missing_facts": [],
        "chunk_fact_recall": 0.0,
        "error_type": "ManifestValidationError",
        "error": benchmark.SAFE_ERROR_MESSAGE,
    }
    assert report["results"][1]["id"] == "clean-policy"
    assert report["results"][1]["status"] == "parsed"


@pytest.mark.asyncio
async def test_run_context_is_reproducible_and_non_sensitive(monkeypatch):
    secret = "credential=must-not-appear"
    monkeypatch.setenv("SMARTCS_TEST_SECRET", secret)

    report = await benchmark.run_benchmark(
        FIXTURE_DIR, environment_label="local-cpu"
    )
    context = report["run_context"]
    serialized = json.dumps(report)

    assert context["environment_label"] == "local-cpu"
    assert context["manifest"]["schema_version"] == 1
    assert len(context["manifest"]["sha256"]) == 64
    assert context["git_revision"] is None or len(context["git_revision"]) == 40
    assert context["python"]["version"]
    assert context["python"]["implementation"]
    assert set(context["platform"]) == {"system", "release", "machine"}
    assert set(context["packages"]) == {"PyMuPDF", "python-docx", "openpyxl"}
    assert context["chunking"] == {
        "CHUNK_SIZE": 800,
        "CHUNK_OVERLAP": 100,
        "MAX_CHUNK_SIZE": 1000,
    }
    assert secret not in serialized
    assert str(Path.cwd().resolve()) not in serialized
    assert getpass.getuser() not in serialized


def test_benchmark_cli_writes_json(tmp_path):
    output = tmp_path / "baseline.json"

    exit_code = benchmark.main(
        [
            "--fixture-dir",
            str(FIXTURE_DIR.resolve()),
            "--output",
            str(output),
            "--environment-label",
            "local-cpu",
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["found_facts"] == 16
    assert payload["run_context"]["environment_label"] == "local-cpu"


def test_benchmark_cli_structured_mode_writes_distinct_report(tmp_path, monkeypatch):
    output = tmp_path / "structured.json"

    async def fake_run(fixture_dir, environment_label):
        assert fixture_dir == FIXTURE_DIR.resolve()
        assert environment_label == "local-cpu"
        return {
            "schema_version": 2,
            "benchmark": "smartcs-structured-parser",
            "mode": "structured",
            "summary": {"acceptance_gate": "passed"},
        }

    monkeypatch.setattr(benchmark, "run_structured_benchmark", fake_run)

    exit_code = benchmark.main(
        [
            "--mode",
            "structured",
            "--fixture-dir",
            str(FIXTURE_DIR.resolve()),
            "--output",
            str(output),
            "--environment-label",
            "local-cpu",
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["mode"] == "structured"
    assert payload["benchmark"] == "smartcs-structured-parser"


def test_benchmark_cli_prints_valid_json_without_output(capsys):
    exit_code = benchmark.main(["--fixture-dir", str(FIXTURE_DIR.resolve())])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["total"] == 9
    assert payload["run_context"]["environment_label"] == "local-unspecified"


def test_benchmark_script_runs_directly(tmp_path):
    output = tmp_path / "baseline.json"
    script = (Path(__file__).parents[1] / "scripts" / "benchmark_document_ingestion.py").resolve()

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--fixture-dir",
            str(FIXTURE_DIR.resolve()),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["summary"]["total"] == 9
