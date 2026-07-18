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
    assert report["summary"]["total"] == 9
    assert results["clean-policy"]["status"] == "parsed"
    assert results["clean-policy"]["fact_recall"] == 1.0
    assert results["scanned-policy"]["status"] == "error"
    assert results["mixed-policy"]["status"] == "parsed"
    assert (
        "\u9a7b\u5916\u8865\u8d34\u6807\u51c6\u4e3a\u6bcf\u67083000\u5143\u3002"
        in results["mixed-policy"]["missing_facts"]
    )
    assert results["encrypted-policy"]["status"] == "error"


def test_benchmark_cli_writes_json(tmp_path):
    output = tmp_path / "baseline.json"

    exit_code = benchmark.main(
        ["--fixture-dir", str(FIXTURE_DIR), "--output", str(output)]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["total"] == 9


def test_benchmark_script_runs_directly(tmp_path):
    output = tmp_path / "baseline.json"
    script = Path(__file__).parents[1] / "scripts" / "benchmark_document_ingestion.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--fixture-dir",
            str(FIXTURE_DIR),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["summary"]["total"] == 9
