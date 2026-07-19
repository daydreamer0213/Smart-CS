import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import scripts.evaluate_rag_retrieval as rag_evaluation
from app.models.document import Document, DocumentFamily
from scripts.evaluate_rag_retrieval import (
    evaluate_results,
    load_rag_manifest,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "documents"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def d_work_dir():
    path = Path("D:/DevData/smartcs/pytest-rag-eval") / uuid.uuid4().hex
    yield path
    shutil.rmtree(path, ignore_errors=True)


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


def test_load_rag_corpus_validates_curated_fixture_and_fact_coverage():
    corpus = rag_evaluation.load_rag_corpus(FIXTURE_DIR)

    assert corpus["origin"] == "curated-retrieval-corpus"
    assert corpus["source_parser_gate"] == "smartcs-structured-parser"
    assert len(corpus["chunks"]) == 12
    assert len({chunk["id"] for chunk in corpus["chunks"]}) == 12
    assert {chunk["fixture_id"] for chunk in corpus["chunks"]} == {
        "clean-policy",
        "repeated-headers",
        "leave-table",
        "scanned-policy",
        "mixed-policy",
        "two-column-policy",
        "headed-docx",
        "multi-sheet-xlsx",
    }


def _write_rag_corpus(tmp_path: Path, mutate) -> Path:
    corpus = json.loads((FIXTURE_DIR / "rag_corpus.json").read_text(encoding="utf-8"))
    mutate(corpus)
    path = tmp_path / "rag_corpus.json"
    path.write_text(json.dumps(corpus, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda corpus: corpus["chunks"].pop(), "12 unique chunks"),
        (
            lambda corpus: corpus["chunks"][0].update(fixture_id="encrypted-policy"),
            "indexable fixtures",
        ),
        (
            lambda corpus: corpus["chunks"][0].update(content="fact removed"),
            "required fact",
        ),
        (
            lambda corpus: corpus["chunks"][0].update(page_end=1),
            "fact provenance",
        ),
    ],
)
def test_load_rag_corpus_rejects_invalid_curated_corpus(tmp_path, mutate, message):
    corpus_path = _write_rag_corpus(tmp_path, mutate)

    with pytest.raises(ValueError, match=message):
        rag_evaluation.load_rag_corpus(FIXTURE_DIR, corpus_path)


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


def test_evaluate_results_accepts_chunk_spanning_expected_fact_pages():
    manifest = load_rag_manifest(FIXTURE_DIR)
    query = next(
        query for query in manifest["queries"] if query["id"] == "annual-leave-application"
    )

    report = evaluate_results(
        {**manifest, "queries": [query]},
        {
            query["id"]: [
                {
                    "title": query["expected"]["title"],
                    "content": query["expected"]["required_text"],
                    "page_start": 1,
                    "page_end": 3,
                    "section_path": query["expected"]["section_path"],
                    "retrievers": ["bm25"],
                }
            ]
        },
    )

    assert report["summary"]["provenance_accuracy"] == 1.0
    assert report["summary"]["gate"] == "passed"


def test_evaluate_results_keeps_one_sanitized_row_per_query_without_hits():
    manifest = load_rag_manifest(FIXTURE_DIR)

    report = evaluate_results(manifest, {})

    assert len(report["results"]) == 12
    assert all(item["rank"] is None for item in report["results"])
    assert all(item["retrievers"] == [] for item in report["results"])


def test_run_evaluation_rejects_non_d_work_dir_on_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(rag_evaluation.os, "name", "nt")

    with pytest.raises(ValueError, match="D:"):
        rag_evaluation.run_evaluation(FIXTURE_DIR, tmp_path, "test")


def test_import_does_not_load_parser_or_retrieval_stack():
    command = [
        sys.executable,
        "-c",
        (
            "import json, sys; "
            "import scripts.evaluate_rag_retrieval; "
            "heavy_roots = {'chromadb', 'sqlalchemy', 'langchain_core', 'langgraph'}; "
            "heavy_modules = sorted(name for name in sys.modules "
            "if name.split('.')[0] in heavy_roots "
            "or name.startswith('app.core.agent') "
            "or name.startswith('app.core.retrieval') "
            "or name.startswith('app.core.parsing')); "
            "print(json.dumps(heavy_modules))"
        ),
    ]

    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == []


def test_run_evaluation_uses_governed_documents_and_real_tool_boundary(
    d_work_dir, monkeypatch,
):
    from app.core.agent import tools as agent_tools

    original_tool = agent_tools.search_knowledge
    observed = {"queries": [], "governance_checked": False}

    class SearchToolSpy:
        async def ainvoke(self, payload):
            observed["queries"].append(payload["query"])
            runtime = agent_tools._runtime.get()
            session = runtime["db_session"]
            families = session.query(DocumentFamily).all()
            documents = session.query(Document).all()
            assert runtime["role"] == "employee"
            assert families
            assert all(document.status == "ready" for document in documents)
            assert all(document.review_status == "approved" for document in documents)
            assert all(
                family.current_document_id
                == next(document.id for document in documents if document.family_id == family.id)
                for family in families
            )
            observed["governance_checked"] = True
            return await original_tool.ainvoke(payload)

    monkeypatch.setattr(agent_tools, "search_knowledge", SearchToolSpy())

    report = rag_evaluation.run_evaluation(FIXTURE_DIR, d_work_dir, "pytest")

    assert report["corpus"]["excluded_fixture_ids"] == ["encrypted-policy"]
    assert report["corpus"]["origin"] == "curated-retrieval-corpus"
    assert report["corpus"]["source_parser_gate"] == "smartcs-structured-parser"
    assert report["corpus"]["indexed_fixture_count"] == 8
    assert report["corpus"]["indexed_chunk_count"] == 12
    assert set(report["run_context"]["manifest_sha256"]) == {
        "manifest",
        "rag_manifest",
        "rag_corpus",
        "combined",
    }
    assert observed["governance_checked"] is True
    assert len(observed["queries"]) == report["query_count"] == 12
    assert report["retriever_profile"] == {
        "embedding": "hash-64",
        "vector": "chroma-cosine",
        "lexical": "bm25",
        "fusion": "rrf",
        "top_k": 3,
    }

    run_dirs = list(d_work_dir.iterdir())
    assert len(run_dirs) == 1
    database_path = run_dirs[0] / "evaluation.db"
    assert database_path.is_file()
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    session = sessionmaker(bind=engine)()
    try:
        assert session.query(DocumentFamily).count() == 8
        assert session.query(Document).count() == 8
    finally:
        session.close()
        engine.dispose()

    serialized = json.dumps(report, ensure_ascii=False)
    assert "工龄满十年的员工每年享有十天年假。" not in serialized
    assert "sk-secret-value" not in serialized
    assert str(FIXTURE_DIR.resolve()) not in serialized
    assert str(d_work_dir.resolve()) not in serialized


def test_cli_rejects_non_d_output_on_windows(d_work_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(rag_evaluation.os, "name", "nt")

    with pytest.raises(ValueError, match="D:"):
        rag_evaluation.main([
            "--fixture-dir", str(FIXTURE_DIR),
            "--work-dir", str(d_work_dir),
            "--output", str(tmp_path / "report.json"),
            "--environment-label", "pytest",
        ])


@pytest.mark.parametrize(("gate", "expected_exit"), [("passed", 0), ("failed", 1)])
def test_cli_writes_report_and_returns_gate_exit_code(
    gate, expected_exit, d_work_dir, monkeypatch,
):
    output = d_work_dir / "report.json"
    monkeypatch.setattr(
        rag_evaluation,
        "run_evaluation",
        lambda *_args: {"summary": {"gate": gate}},
    )

    exit_code = rag_evaluation.main([
        "--fixture-dir", str(FIXTURE_DIR),
        "--work-dir", str(d_work_dir / "runs"),
        "--output", str(output),
        "--environment-label", "pytest",
    ])

    assert exit_code == expected_exit
    assert json.loads(output.read_text(encoding="utf-8"))["summary"]["gate"] == gate
