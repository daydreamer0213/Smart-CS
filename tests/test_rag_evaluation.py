from pathlib import Path

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


def test_evaluate_results_reports_passing_gate_without_chunk_text():
    manifest = load_rag_manifest(FIXTURE_DIR)
    results_by_query = {
        query["id"]: [
            {
                "filename": query["expected"]["filename"],
                "content": query["expected"]["required_text"],
                "page_start": query["expected"]["page_start"],
                "page_end": query["expected"]["page_end"],
                "section_path": query["expected"]["section_path"],
                "retrievers": ["vector", "bm25"],
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


def test_evaluate_results_fails_gate_for_missing_relevance_and_provenance():
    manifest = load_rag_manifest(FIXTURE_DIR)
    query = manifest["queries"][0]
    results_by_query = {
        item["id"]: [] for item in manifest["queries"]
    }
    results_by_query[query["id"]] = [
        {
            "filename": query["expected"]["filename"],
            "content": query["expected"]["required_text"],
            "page_start": 999,
            "page_end": 999,
            "section_path": ["wrong"],
            "retrievers": ["bm25"],
        }
    ]

    report = evaluate_results(manifest, results_by_query)

    assert report["summary"]["gate"] == "failed"
    assert report["summary"]["recall_at_k"] < 0.90
    assert report["summary"]["provenance_accuracy"] < 1.0
    assert set(report["failed_query_ids"]) == {item["id"] for item in manifest["queries"]}
