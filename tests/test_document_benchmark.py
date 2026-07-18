import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import benchmark_document_ingestion as benchmark

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "documents"


@pytest.mark.asyncio
async def test_baseline_benchmark_records_known_pdf_limits():
    report = await benchmark.run_benchmark(FIXTURE_DIR)
    results = {item["id"]: item for item in report["results"]}

    assert report["schema_version"] == 1
    assert report["summary"] == {
        "total": 9,
        "parsed": 7,
        "errors": 2,
        "required_facts": 18,
        "found_facts": 16,
        "fact_recall": 16 / 18,
    }
    assert results["clean-policy"]["status"] == "parsed"
    assert results["clean-policy"]["fact_recall"] == 1.0
    assert results["scanned-policy"]["status"] == "error"
    assert results["mixed-policy"]["status"] == "parsed"
    assert (
        "\u9a7b\u5916\u8865\u8d34\u6807\u51c6\u4e3a\u6bcf\u67083000\u5143\u3002"
        in results["mixed-policy"]["missing_facts"]
    )
    assert results["encrypted-policy"]["status"] == "error"


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


def test_benchmark_cli_writes_json(tmp_path):
    output = tmp_path / "baseline.json"

    exit_code = benchmark.main(
        ["--fixture-dir", str(FIXTURE_DIR.resolve()), "--output", str(output)]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["found_facts"] == 16


def test_benchmark_cli_prints_valid_json_without_output(capsys):
    exit_code = benchmark.main(["--fixture-dir", str(FIXTURE_DIR.resolve())])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["total"] == 9


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
