import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.parsing.chunker import chunk_text
from app.core.parsing.parser import parse_file

SAFE_ERROR_MESSAGE = "Document processing failed."


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
            "error": SAFE_ERROR_MESSAGE,
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
    parser = argparse.ArgumentParser(
        description="Benchmark SmartCS baseline document ingestion"
    )
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
