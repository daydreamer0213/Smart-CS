import argparse
import asyncio
import hashlib
from importlib import metadata
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.parsing.chunker import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    MAX_CHUNK_SIZE,
    chunk_text,
)
from app.core.parsing.parser import parse_file

SAFE_ERROR_MESSAGE = "Document processing failed."
INVALID_MANIFEST_ERROR_TYPE = "ManifestValidationError"
_CASE_STRING_FIELDS = (
    "id",
    "filename",
    "format",
    "category",
    "expected_baseline_status",
)


def _normalize_case(case: object) -> dict | None:
    if not isinstance(case, dict):
        return None
    if any(not isinstance(case.get(field), str) for field in _CASE_STRING_FIELDS):
        return None
    required = case.get("required_facts")
    missing = case.get("expected_missing_facts")
    chunk_count = case.get("expected_chunk_count")
    if not (
        isinstance(required, list)
        and all(isinstance(fact, str) for fact in required)
        and isinstance(missing, list)
        and all(isinstance(fact, str) for fact in missing)
        and set(missing) <= set(required)
        and type(chunk_count) is int
        and chunk_count >= 0
        and case["expected_baseline_status"] in {"parsed", "error"}
    ):
        return None
    if "expected_page_count" in case and (
        type(case["expected_page_count"]) is not int
        or case["expected_page_count"] < 0
    ):
        return None
    normalized = {
        field: case[field]
        for field in (*_CASE_STRING_FIELDS, "required_facts", "expected_missing_facts", "expected_chunk_count")
    }
    if "expected_page_count" in case:
        normalized["expected_page_count"] = case["expected_page_count"]
    return normalized


def _invalid_manifest_result(index: int) -> dict:
    return {
        "id": f"invalid-manifest-entry-{index}",
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
        "error_type": INVALID_MANIFEST_ERROR_TYPE,
        "error": SAFE_ERROR_MESSAGE,
    }


def _git_revision() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    revision = completed.stdout.strip()
    return revision if completed.returncode == 0 and len(revision) == 40 else None


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "unknown"


def _run_context(manifest: dict, manifest_bytes: bytes, environment_label: str) -> dict:
    return {
        "environment_label": environment_label,
        "manifest": {
            "schema_version": manifest.get("schema_version"),
            "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        },
        "git_revision": _git_revision(),
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "packages": {
            name: _package_version(name)
            for name in ("PyMuPDF", "python-docx", "openpyxl")
        },
        "chunking": {
            "CHUNK_SIZE": CHUNK_SIZE,
            "CHUNK_OVERLAP": CHUNK_OVERLAP,
            "MAX_CHUNK_SIZE": MAX_CHUNK_SIZE,
        },
    }


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
        "page_count": None,
    }
    try:
        base["page_count"] = _page_count(path)
        text = parse_file(path.name, path.read_bytes())
        chunks = await chunk_text(text)
        found = [fact for fact in case["required_facts"] if fact in text]
        missing = [fact for fact in case["required_facts"] if fact not in text]
        chunk_found = [
            fact for fact in case["required_facts"] if any(fact in chunk for chunk in chunks)
        ]
        chunk_missing = [
            fact for fact in case["required_facts"] if fact not in chunk_found
        ]
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
            "chunk_found_facts": chunk_found,
            "chunk_missing_facts": chunk_missing,
            "chunk_fact_recall": len(chunk_found) / required if required else 1.0,
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
            "chunk_found_facts": [],
            "chunk_missing_facts": case["required_facts"],
            "chunk_fact_recall": 0.0,
            "error_type": type(exc).__name__,
            "error": SAFE_ERROR_MESSAGE,
        }


async def run_benchmark(
    fixture_dir: Path, environment_label: str = "local-unspecified"
) -> dict:
    manifest_bytes = (fixture_dir / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    results = []
    valid_cases = []
    for index, raw_case in enumerate(manifest["fixtures"], start=1):
        case = _normalize_case(raw_case)
        if case is None:
            results.append(_invalid_manifest_result(index))
            continue
        valid_cases.append(case)
        results.append(await _benchmark_fixture(fixture_dir, case))
    required = sum(len(case["required_facts"]) for case in valid_cases)
    found = sum(len(item["found_facts"]) for item in results)
    return {
        "schema_version": 1,
        "benchmark": "smartcs-baseline-parser",
        "run_context": _run_context(manifest, manifest_bytes, environment_label),
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
    parser = argparse.ArgumentParser(
        description="Benchmark SmartCS baseline document ingestion"
    )
    parser.add_argument("--fixture-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--environment-label", default="local-unspecified")
    args = parser.parse_args(argv)
    report = asyncio.run(run_benchmark(args.fixture_dir, args.environment_label))
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
