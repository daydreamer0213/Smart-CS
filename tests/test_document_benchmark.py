import getpass
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts import benchmark_document_ingestion as benchmark

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "documents"


def load_manifest():
    return json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))


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
