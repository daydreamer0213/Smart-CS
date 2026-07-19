import argparse
import asyncio
import hashlib
from importlib import metadata
import json
import os
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
from app.config import settings
from app.core.parsing.quality import evaluate_parse_quality
from app.core.parsing.router import parse_structured_file
from app.core.parsing.runtime import configure_parser_runtime
from app.core.parsing.structured_chunker import MAX_TOKENS, chunk_document

SAFE_ERROR_MESSAGE = "Document processing failed."
SAFE_BLOCKED_MESSAGE = "Document is not eligible for indexing."
INVALID_MANIFEST_ERROR_TYPE = "ManifestValidationError"
_CASE_STRING_FIELDS = (
    "id",
    "filename",
    "format",
    "category",
    "expected_baseline_status",
)
_STRUCTURED_STRING_FIELDS = (
    "expected_structured_status",
    "expected_route",
    "expected_route_reason",
    "expected_quality_status",
)
_SAFE_ELEMENT_METADATA = frozenset(
    {"ocr", "sheet_name", "row_start", "row_end"}
)
_STRUCTURED_CORPUS_FIXTURE_IDS = frozenset(
    {
        "clean-policy",
        "repeated-headers",
        "leave-table",
        "scanned-policy",
        "mixed-policy",
        "two-column-policy",
        "encrypted-policy",
        "headed-docx",
        "multi-sheet-xlsx",
    }
)
_STRUCTURED_CORPUS_REQUIRED_FACTS = 18


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


def _normalize_structured_case(case: object) -> dict | None:
    normalized = _normalize_case(case)
    if normalized is None or not isinstance(case, dict):
        return None
    if any(not isinstance(case.get(field), str) for field in _STRUCTURED_STRING_FIELDS):
        return None
    warnings = case.get("expected_quality_warnings")
    provenance = case.get("expected_fact_provenance")
    fact_order = case.get("expected_fact_order")
    associations = case.get("expected_table_associations")
    if not (
        case["expected_structured_status"] in {"parsed", "blocked"}
        and case["expected_route"] in {"native", "advanced", "rejected"}
        and case["expected_quality_status"] in {"passed", "review_required", "failed"}
        and isinstance(warnings, list)
        and all(isinstance(item, str) for item in warnings)
        and type(case.get("expected_indexable")) is bool
        and isinstance(provenance, list)
        and isinstance(fact_order, list)
        and all(isinstance(fact, str) for fact in fact_order)
        and set(fact_order) <= set(normalized["required_facts"])
        and isinstance(associations, list)
        and all(
            isinstance(group, list)
            and len(group) >= 2
            and all(isinstance(fact, str) for fact in group)
            and set(group) <= set(normalized["required_facts"])
            for group in associations
        )
    ):
        return None

    normalized_provenance = []
    for item in provenance:
        if not isinstance(item, dict):
            return None
        fact = item.get("fact")
        page_start = item.get("page_start")
        page_end = item.get("page_end")
        section_path = item.get("section_path")
        expected_metadata = item.get("metadata", {})
        if not (
            isinstance(fact, str)
            and (page_start is None or type(page_start) is int and page_start >= 1)
            and (page_end is None or type(page_end) is int and page_end >= 1)
            and isinstance(section_path, list)
            and all(isinstance(part, str) for part in section_path)
            and isinstance(expected_metadata, dict)
            and all(key in _SAFE_ELEMENT_METADATA for key in expected_metadata)
        ):
            return None
        normalized_provenance.append(
            {
                "fact": fact,
                "page_start": page_start,
                "page_end": page_end,
                "section_path": section_path,
                "metadata": expected_metadata,
            }
        )
    if [item["fact"] for item in normalized_provenance] != normalized["required_facts"]:
        return None

    normalized.update(
        {field: case[field] for field in _STRUCTURED_STRING_FIELDS}
    )
    normalized.update(
        {
            "expected_quality_warnings": warnings,
            "expected_indexable": case["expected_indexable"],
            "expected_fact_provenance": normalized_provenance,
            "expected_fact_order": fact_order,
            "expected_table_associations": associations,
        }
    )
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


def _invalid_structured_manifest_result(index: int) -> dict:
    return {
        **_invalid_manifest_result(index),
        "route": None,
        "route_reason": None,
        "parser": None,
        "chunker": {"name": "smartcs-structured", "version": "1"},
        "parse_elapsed_ms": 0.0,
        "chunk_elapsed_ms": 0.0,
        "quality": None,
        "indexable": False,
        "safe_reason": SAFE_ERROR_MESSAGE,
        "elements": [],
        "chunks": [],
        "fact_evidence": [],
        "table_associations": [],
        "reading_order": {"facts": [], "offsets": [], "passed": False},
        "provenance_passed": False,
        "acceptance_passed": False,
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


def _tesseract_version() -> str:
    try:
        completed = subprocess.run(
            [settings.tesseract_cmd, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    first_line = completed.stdout.splitlines()[0].strip() if completed.stdout else ""
    return first_line or "unavailable"


def _structured_run_context(
    manifest: dict, manifest_bytes: bytes, environment_label: str
) -> dict:
    context = _run_context(manifest, manifest_bytes, environment_label)
    context["packages"]["docling-slim"] = _package_version("docling-slim")
    context["hardware"] = {
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpu_count": os.cpu_count(),
    }
    context["ocr"] = {
        "engine": "tesseract-cli",
        "version": _tesseract_version(),
        "languages": ["chi_sim", "eng"],
    }
    context["structured_chunking"] = {
        "chunker": "smartcs-structured",
        "version": "1",
        "max_tokens": MAX_TOKENS,
    }
    return context


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


def _normalized_text(text: str) -> str:
    return "".join(text.split())


def _safe_metadata(values: dict) -> dict:
    return {
        key: value
        for key, value in values.items()
        if key in _SAFE_ELEMENT_METADATA
        and isinstance(value, (str, int, float, bool, type(None)))
    }


def _element_record(index: int, element) -> dict:
    return {
        "index": index,
        "element_type": element.element_type,
        "page_start": element.page_start,
        "page_end": element.page_end,
        "section_path": element.section_path,
        "metadata": _safe_metadata(element.metadata),
    }


def _chunk_record(index: int, chunk) -> dict:
    return {
        "index": index,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "section_path": chunk.section_path,
        "element_types": chunk.element_types,
        "source_element_indexes": chunk.source_element_indexes,
        "token_count": chunk.token_count,
    }


def _contains_fact(text: str, fact: str) -> bool:
    return _normalized_text(fact) in _normalized_text(text)


def _fact_evidence(fact: str, elements: list, chunks: list) -> dict:
    return {
        "fact": fact,
        "elements": [
            _element_record(index, element)
            for index, element in enumerate(elements)
            if _contains_fact(element.text, fact)
        ],
        "chunks": [
            _chunk_record(index, chunk)
            for index, chunk in enumerate(chunks)
            if _contains_fact(chunk.content, fact)
        ],
    }


def _chunk_covers_expected(chunk: dict, expected: dict) -> bool:
    expected_start = expected["page_start"]
    expected_end = expected["page_end"]
    if expected_start is None:
        page_matches = chunk["page_start"] is None and chunk["page_end"] is None
    else:
        page_matches = (
            chunk["page_start"] is not None
            and chunk["page_end"] is not None
            and chunk["page_start"] <= expected_start
            and chunk["page_end"] >= expected_end
        )
    return page_matches and chunk["section_path"] == expected["section_path"]


def _fact_provenance_passed(evidence: dict, expected: dict) -> bool:
    matching_elements = [
        item
        for item in evidence["elements"]
        if item["page_start"] == expected["page_start"]
        and item["page_end"] == expected["page_end"]
        and item["section_path"] == expected["section_path"]
        and all(
            item["metadata"].get(key) == value
            for key, value in expected["metadata"].items()
        )
    ]
    matching_indexes = {item["index"] for item in matching_elements}
    matching_chunks = [
        item
        for item in evidence["chunks"]
        if _chunk_covers_expected(item, expected)
        and matching_indexes.intersection(item["source_element_indexes"])
    ]
    return bool(matching_elements and matching_chunks)


def _table_association(group: list[str], elements: list, chunks: list) -> dict:
    def same_row(text: str) -> bool:
        return any(
            all(_contains_fact(line, fact) for fact in group)
            for line in text.splitlines()
        )

    element_indexes = [
        index
        for index, element in enumerate(elements)
        if element.element_type == "table"
        and same_row(element.text)
    ]
    chunk_indexes = [
        index
        for index, chunk in enumerate(chunks)
        if "table" in chunk.element_types
        and same_row(chunk.content)
    ]
    matching_element_indexes = set(element_indexes)
    lineage_matches = any(
        matching_element_indexes.intersection(chunks[index].source_element_indexes)
        for index in chunk_indexes
    )
    return {
        "facts": group,
        "element_indexes": element_indexes,
        "chunk_indexes": chunk_indexes,
        "passed": lineage_matches,
    }


def _reading_order(facts: list[str], text: str) -> dict:
    normalized = _normalized_text(text)
    offsets = [normalized.find(_normalized_text(fact)) for fact in facts]
    return {
        "facts": facts,
        "offsets": offsets,
        "passed": all(offset >= 0 for offset in offsets) and offsets == sorted(offsets),
    }


async def _benchmark_structured_fixture(fixture_dir: Path, case: dict) -> dict:
    path = fixture_dir / case["filename"]
    started = time.perf_counter()
    base = {
        "id": case["id"],
        "filename": case["filename"],
        "format": case["format"],
        "category": case["category"],
        "expected_structured_status": case["expected_structured_status"],
        "page_count": None,
    }
    try:
        parse_started = time.perf_counter()
        document = parse_structured_file(path.name, path.read_bytes())
        parse_elapsed_ms = (time.perf_counter() - parse_started) * 1000
        quality = evaluate_parse_quality(
            document,
            elapsed_ms=parse_elapsed_ms,
            warnings=document.quality.warnings,
        )
        chunk_started = time.perf_counter()
        chunks = (
            chunk_document(document, path.stem)
            if quality.status == "passed" and document.elements
            else []
        )
        chunk_elapsed_ms = (time.perf_counter() - chunk_started) * 1000
        route = document.metadata.get("route", "native")
        route_reason = document.metadata.get("route_reason", "native_format")
        evidence = [
            _fact_evidence(fact, document.elements, chunks)
            for fact in case["required_facts"]
        ]
        expected_by_fact = {
            item["fact"]: item for item in case["expected_fact_provenance"]
        }
        provenance_passed = all(
            _fact_provenance_passed(item, expected_by_fact[item["fact"]])
            for item in evidence
        )
        associations = [
            _table_association(group, document.elements, chunks)
            for group in case["expected_table_associations"]
        ]
        reading_order = _reading_order(
            case["expected_fact_order"], document.plain_text
        )
        found = [item["fact"] for item in evidence if item["elements"]]
        chunk_found = [item["fact"] for item in evidence if item["chunks"]]
        required = len(case["required_facts"])
        status = "parsed" if quality.status == "passed" else "blocked"
        indexable = status == "parsed" and bool(chunks)
        acceptance_passed = all(
            (
                status == case["expected_structured_status"],
                route == case["expected_route"],
                route_reason == case["expected_route_reason"],
                quality.status == case["expected_quality_status"],
                set(case["expected_quality_warnings"]) == set(quality.warnings),
                indexable == case["expected_indexable"],
                len(found) == required,
                len(chunk_found) == required,
                provenance_passed,
                all(item["passed"] for item in associations),
                reading_order["passed"],
            )
        )
        return {
            **base,
            "status": status,
            "route": route,
            "route_reason": route_reason,
            "parser": {
                "name": document.parser_name,
                "version": document.parser_version,
            },
            "chunker": {"name": "smartcs-structured", "version": "1"},
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "parse_elapsed_ms": round(parse_elapsed_ms, 3),
            "chunk_elapsed_ms": round(chunk_elapsed_ms, 3),
            "page_count": document.page_count,
            "character_count": len(document.plain_text),
            "chunk_count": len(chunks),
            "quality": quality.model_dump(),
            "indexable": indexable,
            "safe_reason": None if status == "parsed" else SAFE_BLOCKED_MESSAGE,
            "elements": [
                _element_record(index, element)
                for index, element in enumerate(document.elements)
            ],
            "chunks": [
                _chunk_record(index, chunk) for index, chunk in enumerate(chunks)
            ],
            "found_facts": found,
            "missing_facts": [
                fact for fact in case["required_facts"] if fact not in found
            ],
            "fact_recall": len(found) / required if required else 1.0,
            "chunk_found_facts": chunk_found,
            "chunk_missing_facts": [
                fact for fact in case["required_facts"] if fact not in chunk_found
            ],
            "chunk_fact_recall": len(chunk_found) / required if required else 1.0,
            "fact_evidence": evidence,
            "table_associations": associations,
            "reading_order": reading_order,
            "provenance_passed": provenance_passed,
            "acceptance_passed": acceptance_passed,
            "error_type": None,
            "error": None,
        }
    except Exception as exc:
        required = case["required_facts"]
        return {
            **base,
            "status": "error",
            "route": None,
            "route_reason": None,
            "parser": None,
            "chunker": {"name": "smartcs-structured", "version": "1"},
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "parse_elapsed_ms": 0.0,
            "chunk_elapsed_ms": 0.0,
            "character_count": 0,
            "chunk_count": 0,
            "quality": None,
            "indexable": False,
            "safe_reason": SAFE_ERROR_MESSAGE,
            "elements": [],
            "chunks": [],
            "found_facts": [],
            "missing_facts": required,
            "fact_recall": 0.0,
            "chunk_found_facts": [],
            "chunk_missing_facts": required,
            "chunk_fact_recall": 0.0,
            "fact_evidence": [],
            "table_associations": [],
            "reading_order": {
                "facts": case["expected_fact_order"],
                "offsets": [],
                "passed": False,
            },
            "provenance_passed": False,
            "acceptance_passed": False,
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


async def run_structured_benchmark(
    fixture_dir: Path, environment_label: str = "local-unspecified"
) -> dict:
    configure_parser_runtime()
    manifest_bytes = (fixture_dir / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    results = []
    valid_cases = []
    for index, raw_case in enumerate(manifest["fixtures"], start=1):
        case = _normalize_structured_case(raw_case)
        if case is None:
            results.append(_invalid_structured_manifest_result(index))
            continue
        valid_cases.append(case)
        results.append(await _benchmark_structured_fixture(fixture_dir, case))

    required = sum(len(case["required_facts"]) for case in valid_cases)
    found = sum(len(item["found_facts"]) for item in results)
    chunk_found = sum(len(item["chunk_found_facts"]) for item in results)
    corpus_gate = (
        len(valid_cases) == len(_STRUCTURED_CORPUS_FIXTURE_IDS)
        and {case["id"] for case in valid_cases} == _STRUCTURED_CORPUS_FIXTURE_IDS
        and required == _STRUCTURED_CORPUS_REQUIRED_FACTS
    )
    fact_gate = found == required
    chunk_gate = chunk_found == required
    provenance_gate = all(item["provenance_passed"] for item in results)
    acceptance_gate = (
        corpus_gate
        and fact_gate
        and chunk_gate
        and provenance_gate
        and all(item["acceptance_passed"] for item in results)
    )
    return {
        "schema_version": 2,
        "benchmark": "smartcs-structured-parser",
        "mode": "structured",
        "run_context": _structured_run_context(
            manifest, manifest_bytes, environment_label
        ),
        "results": results,
        "summary": {
            "total": len(results),
            "parsed": sum(item["status"] == "parsed" for item in results),
            "blocked": sum(item["status"] == "blocked" for item in results),
            "errors": sum(item["status"] == "error" for item in results),
            "required_facts": required,
            "found_facts": found,
            "chunk_found_facts": chunk_found,
            "fact_recall": found / required if required else 1.0,
            "chunk_fact_recall": chunk_found / required if required else 1.0,
            "corpus_gate": "passed" if corpus_gate else "failed",
            "parsed_fact_gate": "passed" if fact_gate else "failed",
            "chunk_fact_gate": "passed" if chunk_gate else "failed",
            "provenance_gate": "passed" if provenance_gate else "failed",
            "acceptance_gate": "passed" if acceptance_gate else "failed",
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark SmartCS document ingestion"
    )
    parser.add_argument("--mode", choices=("baseline", "structured"), default="baseline")
    parser.add_argument("--fixture-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--environment-label", default="local-unspecified")
    args = parser.parse_args(argv)
    benchmark_runner = (
        run_structured_benchmark if args.mode == "structured" else run_benchmark
    )
    report = asyncio.run(benchmark_runner(args.fixture_dir, args.environment_label))
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    if args.mode == "structured" and report["summary"].get("acceptance_gate") != "passed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
