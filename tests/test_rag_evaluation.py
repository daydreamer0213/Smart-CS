import json
from pathlib import Path

import pytest

from scripts.evaluate_rag_retrieval import evaluate_results, load_rag_manifest


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "documents"


def test_load_rag_manifest_defines_indexable_golden_queries():
    manifest = load_rag_manifest(FIXTURE_DIR)

    assert manifest["top_k"] == 3
    assert manifest["minimum_recall_at_k"] == 0.90
    assert manifest["minimum_provenance_accuracy"] == 1.00
    assert len(manifest["queries"]) == 12
    assert len({query["id"] for query in manifest["queries"]}) == 12
    assert all(query["expected"]["indexable"] for query in manifest["queries"])
    assert next(query for query in manifest["queries"] if query["id"] == "marriage-leave")[
        "question"
    ] == "婚假需要一次性休完吗？"


def _write_rag_manifest(tmp_path: Path, mutate) -> Path:
    manifest = json.loads((FIXTURE_DIR / "rag_manifest.json").read_text(encoding="utf-8"))
    mutate(manifest["queries"])
    path = tmp_path / "rag_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return path


def test_load_rag_manifest_rejects_duplicate_fixture_fact_labels(tmp_path):
    def duplicate_label(queries):
        queries[2]["fixture_id"] = queries[1]["fixture_id"]
        queries[2]["required_text"] = queries[1]["required_text"]

    manifest_path = _write_rag_manifest(tmp_path, duplicate_label)

    with pytest.raises(ValueError, match="unique fixture facts"):
        load_rag_manifest(FIXTURE_DIR, manifest_path)


def test_load_rag_manifest_requires_every_indexable_fixture(tmp_path):
    def omit_clean_policy(queries):
        queries[0]["fixture_id"] = "leave-table"
        queries[0]["required_text"] = "工龄"

    manifest_path = _write_rag_manifest(tmp_path, omit_clean_policy)

    with pytest.raises(ValueError, match="all indexable fixtures"):
        load_rag_manifest(FIXTURE_DIR, manifest_path)


def test_evaluate_results_reports_passing_gate_without_chunk_text():
    manifest = load_rag_manifest(FIXTURE_DIR)
    results_by_query = {
        query["id"]: [
            {
                "title": query["expected"]["title"],
                "content": query["expected"]["required_text"] + " SENSITIVE_CHUNK_BODY",
                "page_start": query["expected"]["page_start"],
                "page_end": query["expected"]["page_end"],
                "section_path": query["expected"]["section_path"],
                "retrievers": ["vector", "bm25"],
                "path": "C:\\private\\policy.pdf",
                "api_key": "sk-secret-value",
            }
        ]
        for query in manifest["queries"]
    }

    report = evaluate_results(manifest, results_by_query)

    assert report["summary"] == {
        "recall_at_k": 1.0,
        "mrr": 1.0,
        "provenance_accuracy": 1.0,
        "gate": "passed",
    }
    assert report["failed_query_ids"] == []
    assert all(set(item) == {"query_id", "rank", "retrievers"} for item in report["results"])
    serialized = json.dumps(report)
    assert "SENSITIVE_CHUNK_BODY" not in serialized
    assert "C:\\\\private" not in serialized
    assert "sk-secret-value" not in serialized


def test_evaluate_results_calculates_recall_and_mrr_at_ranks_two_and_three():
    manifest = load_rag_manifest(FIXTURE_DIR)
    results_by_query = {
        query["id"]: [
            {
                "title": query["expected"]["title"],
                "content": query["expected"]["required_text"],
                "page_start": query["expected"]["page_start"],
                "page_end": query["expected"]["page_end"],
                "section_path": query["expected"]["section_path"],
                "retrievers": ["bm25"],
            }
        ]
        for query in manifest["queries"]
    }
    irrelevant = {"title": "unrelated.pdf", "content": "irrelevant", "retrievers": ["bm25"]}
    results_by_query[manifest["queries"][0]["id"]].insert(0, irrelevant)
    results_by_query[manifest["queries"][1]["id"]][:0] = [irrelevant, irrelevant]

    report = evaluate_results(manifest, results_by_query)

    assert report["summary"]["recall_at_k"] == 1.0
    assert report["summary"]["mrr"] == pytest.approx(65 / 72)
    assert report["summary"]["provenance_accuracy"] == 1.0
    assert report["summary"]["gate"] == "passed"


def test_evaluate_results_fails_gate_when_one_recalled_result_has_wrong_provenance():
    manifest = load_rag_manifest(FIXTURE_DIR)
    results_by_query = {
        query["id"]: [
            {
                "title": query["expected"]["title"],
                "content": query["expected"]["required_text"],
                "page_start": query["expected"]["page_start"],
                "page_end": query["expected"]["page_end"],
                "section_path": query["expected"]["section_path"],
                "retrievers": ["bm25"],
            }
        ]
        for query in manifest["queries"]
    }
    failed_query = manifest["queries"][0]
    results_by_query[failed_query["id"]] = [
        {
            "title": failed_query["expected"]["title"],
            "content": failed_query["expected"]["required_text"],
            "page_start": 999,
            "page_end": 999,
            "section_path": ["wrong"],
            "retrievers": ["bm25"],
        }
    ]

    report = evaluate_results(manifest, results_by_query)

    assert report["summary"]["recall_at_k"] == 1.0
    assert report["summary"]["provenance_accuracy"] == pytest.approx(11 / 12)
    assert report["summary"]["gate"] == "failed"
    assert report["failed_query_ids"] == [failed_query["id"]]
