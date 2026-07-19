"""Deterministic metric contract for the M2-5 RAG retrieval gate."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any


def _normalized_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


def load_rag_manifest(fixture_dir: Path, manifest_path: Path | None = None) -> dict:
    """Load golden retrieval cases and resolve their approved fixture evidence."""
    fixture_dir = Path(fixture_dir)
    manifest_path = Path(manifest_path) if manifest_path else fixture_dir / "rag_manifest.json"
    raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    document_manifest = json.loads(
        (fixture_dir / raw_manifest["document_manifest"]).read_text(encoding="utf-8")
    )
    fixtures = {item["id"]: item for item in document_manifest["fixtures"]}
    queries = raw_manifest["queries"]
    query_labels = {
        (item.get("fixture_id"), item.get("required_text")) for item in queries
    }
    indexable_fixture_ids = {
        fixture_id
        for fixture_id, fixture in fixtures.items()
        if fixture.get("expected_indexable") is True
    }
    query_fixture_ids = {item.get("fixture_id") for item in queries}

    if (
        raw_manifest.get("top_k") != 3
        or raw_manifest.get("minimum_recall_at_k") != 0.90
        or raw_manifest.get("minimum_provenance_accuracy") != 1.00
        or len(queries) != 12
        or len({item.get("id") for item in queries}) != 12
    ):
        raise ValueError("Invalid RAG evaluation manifest")
    if len(query_labels) != len(queries):
        raise ValueError("RAG queries must use unique fixture facts")
    if query_fixture_ids != indexable_fixture_ids:
        raise ValueError("RAG queries must cover all indexable fixtures")

    resolved_queries = []
    for query in queries:
        fixture = fixtures.get(query.get("fixture_id"))
        required_text = query.get("required_text")
        if not fixture or not fixture.get("expected_indexable") or required_text not in fixture.get("required_facts", []):
            raise ValueError("RAG query must reference an indexable fixture fact")
        provenance = next(
            (item for item in fixture["expected_fact_provenance"] if item["fact"] == required_text),
            None,
        )
        if not isinstance(query.get("id"), str) or not isinstance(query.get("question"), str) or provenance is None:
            raise ValueError("Invalid RAG query")
        resolved_queries.append(
            {
                "id": query["id"],
                "question": query["question"],
                "expected": {
                    "title": fixture["filename"],
                    "required_text": required_text,
                    "page_start": provenance["page_start"],
                    "page_end": provenance["page_end"],
                    "section_path": provenance["section_path"],
                    "indexable": True,
                },
            }
        )
    return {
        "schema_version": raw_manifest.get("schema_version"),
        "top_k": raw_manifest["top_k"],
        "minimum_recall_at_k": raw_manifest["minimum_recall_at_k"],
        "minimum_provenance_accuracy": raw_manifest["minimum_provenance_accuracy"],
        "queries": resolved_queries,
    }


def _matches_expected(result: dict[str, Any], expected: dict[str, Any]) -> bool:
    return (
        result.get("title") == expected["title"]
        and _normalized_text(expected["required_text"]) in _normalized_text(result.get("content"))
    )


def _has_expected_provenance(result: dict[str, Any], expected: dict[str, Any]) -> bool:
    return (
        result.get("page_start") == expected["page_start"]
        and result.get("page_end") == expected["page_end"]
        and result.get("section_path") == expected["section_path"]
    )


def evaluate_results(manifest: dict, results_by_query: dict[str, list[dict]]) -> dict:
    """Evaluate retrieval output without retaining source text or file paths."""
    rows = []
    failed_query_ids = []
    reciprocal_ranks = []
    provenance_matches = 0
    for query in manifest["queries"]:
        expected = query["expected"]
        rank = next(
            (
                index
                for index, result in enumerate(results_by_query.get(query["id"], [])[: manifest["top_k"]], start=1)
                if _matches_expected(result, expected)
            ),
            None,
        )
        if rank is None:
            failed_query_ids.append(query["id"])
            reciprocal_ranks.append(0.0)
            continue
        result = results_by_query[query["id"]][rank - 1]
        provenance_passed = _has_expected_provenance(result, expected)
        reciprocal_ranks.append(1 / rank)
        provenance_matches += int(provenance_passed)
        if not provenance_passed:
            failed_query_ids.append(query["id"])
        rows.append(
            {
                "query_id": query["id"],
                "rank": rank,
                "retrievers": [
                    source for source in result.get("retrievers", []) if source in {"vector", "bm25"}
                ],
            }
        )

    query_count = len(manifest["queries"])
    recall = sum(rank > 0 for rank in reciprocal_ranks) / query_count
    provenance_accuracy = provenance_matches / query_count
    gate_passed = (
        recall >= manifest["minimum_recall_at_k"]
        and provenance_accuracy >= manifest["minimum_provenance_accuracy"]
    )
    return {
        "results": rows,
        "failed_query_ids": failed_query_ids,
        "summary": {
            "recall_at_k": recall,
            "mrr": sum(reciprocal_ranks) / query_count,
            "provenance_accuracy": provenance_accuracy,
            "gate": "passed" if gate_passed else "failed",
        },
    }
