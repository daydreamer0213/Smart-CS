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
from app.models.document import Document, DocumentChunk, DocumentFamily
from scripts.evaluate_rag_retrieval import evaluate_results, load_rag_manifest


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "documents"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def d_work_dir():
    path = Path("D:/DevData/smartcs/pytest-rag-eval") / uuid.uuid4().hex
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _write_json_copy(source: Path, target: Path, mutate) -> Path:
    payload = json.loads(source.read_text(encoding="utf-8"))
    mutate(payload)
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return target


def _result_for(query, *, retrievers=("bm25",), **overrides):
    expected = query["expected"]
    return {
        "corpus_chunk_id": expected["corpus_chunk_id"],
        "title": expected["title"],
        "content": expected["required_text"],
        "page_start": expected["page_start"],
        "page_end": expected["page_end"],
        "section_path": expected["section_path"],
        "retrievers": list(retrievers),
        **overrides,
    }


def _passing_results(manifest, *, retrievers=("bm25",)):
    return {
        query["id"]: [_result_for(query, retrievers=retrievers)]
        for query in manifest["queries"]
    }


def test_load_rag_corpus_derives_content_only_from_manifest_facts():
    raw = json.loads((FIXTURE_DIR / "rag_corpus.json").read_text(encoding="utf-8"))
    corpus = rag_evaluation.load_rag_corpus(FIXTURE_DIR)

    assert raw["origin"] == "curated-retrieval-corpus"
    assert raw["source_parser_gate"] == "smartcs-structured-parser"
    assert len(raw["chunks"]) == len(corpus["chunks"]) == 11
    assert len({chunk["id"] for chunk in raw["chunks"]}) == 11
    assert all("content" not in chunk for chunk in raw["chunks"])
    assert all(chunk["content"] == "\n".join(chunk["facts"]) for chunk in corpus["chunks"])
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


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda corpus: corpus["chunks"].pop(), "11 unique chunks"),
        (
            lambda corpus: corpus["chunks"][1].update(id=corpus["chunks"][0]["id"]),
            "11 unique chunks",
        ),
        (
            lambda corpus: corpus["chunks"][0].update(fixture_id="encrypted-policy"),
            "indexable fixtures",
        ),
        (
            lambda corpus: corpus["chunks"][0].update(facts=["无来源政策句"]),
            "manifest facts",
        ),
        (
            lambda corpus: corpus["chunks"][0].update(page_end=1),
            "fact provenance",
        ),
        (
            lambda corpus: corpus["chunks"][-2].update(metadata={"sheet_name": "错误表"}),
            "fact metadata",
        ),
        (
            lambda corpus: corpus["chunks"][0].update(content="自由编写的正文"),
            "free content",
        ),
    ],
)
def test_load_rag_corpus_rejects_unverifiable_evidence(tmp_path, mutate, message):
    corpus_path = _write_json_copy(
        FIXTURE_DIR / "rag_corpus.json",
        tmp_path / "rag_corpus.json",
        mutate,
    )

    with pytest.raises(ValueError, match=message):
        rag_evaluation.load_rag_corpus(FIXTURE_DIR, corpus_path)


def test_load_rag_manifest_resolves_stable_source_chunk_and_page_bounds():
    manifest = load_rag_manifest(FIXTURE_DIR)

    assert manifest["top_k"] == 3
    assert manifest["minimum_recall_at_k"] == 0.90
    assert manifest["minimum_provenance_accuracy"] == 1.00
    assert len(manifest["queries"]) == 12
    annual_leave = next(
        query for query in manifest["queries"] if query["id"] == "annual-leave-ten-years"
    )
    assert annual_leave["expected"]["corpus_chunk_id"] == "clean-policy-001"
    assert annual_leave["expected"]["document_page_count"] == 2
    assert next(query for query in manifest["queries"] if query["id"] == "marriage-leave")[
        "question"
    ] == "婚假需要一次性休完吗？"


def _write_rag_manifest(tmp_path: Path, mutate) -> Path:
    return _write_json_copy(
        FIXTURE_DIR / "rag_manifest.json",
        tmp_path / "rag_manifest.json",
        lambda manifest: mutate(manifest["queries"]),
    )


def test_load_rag_manifest_rejects_duplicate_fixture_fact_labels(tmp_path):
    def duplicate_label(queries):
        queries[2]["fixture_id"] = queries[1]["fixture_id"]
        queries[2]["required_text"] = queries[1]["required_text"]
        queries[2]["expected_chunk_id"] = "repeated-headers-001"

    manifest_path = _write_rag_manifest(tmp_path, duplicate_label)

    with pytest.raises(ValueError, match="unique fixture facts"):
        load_rag_manifest(FIXTURE_DIR, manifest_path)


def test_load_rag_manifest_requires_every_indexable_fixture(tmp_path):
    def omit_clean_policy(queries):
        queries[0]["fixture_id"] = "leave-table"
        queries[0]["required_text"] = "工龄"
        queries[0]["expected_chunk_id"] = "leave-table-001"

    manifest_path = _write_rag_manifest(tmp_path, omit_clean_policy)

    with pytest.raises(ValueError, match="all indexable fixtures"):
        load_rag_manifest(FIXTURE_DIR, manifest_path)


def test_load_rag_manifest_rejects_chunk_without_expected_fact(tmp_path):
    manifest_path = _write_rag_manifest(
        tmp_path,
        lambda queries: queries[4].update(expected_chunk_id="leave-table-001"),
    )

    with pytest.raises(ValueError, match="stable source chunk"):
        load_rag_manifest(FIXTURE_DIR, manifest_path)


def test_evaluate_results_requires_stable_chunk_identity_and_sanitizes_report():
    manifest = load_rag_manifest(FIXTURE_DIR)
    results = _passing_results(manifest)
    first = manifest["queries"][0]
    results[first["id"]][0].update(
        corpus_chunk_id="wrong-chunk",
        path="C:\\private\\policy.pdf",
        api_key="sk-secret-value",
    )

    report = evaluate_results(manifest, results)

    assert report["summary"]["recall_at_k"] == pytest.approx(11 / 12)
    assert report["summary"]["provenance_accuracy"] == 1.0
    assert report["summary"]["gate"] == "passed"
    assert report["failed_query_ids"] == [first["id"]]
    assert report["retriever_contributions"] == {
        "bm25_query_hits": 11,
        "vector_query_hits": 0,
    }
    serialized = json.dumps(report)
    assert "C:\\\\private" not in serialized
    assert "sk-secret-value" not in serialized
    assert first["expected"]["required_text"] not in serialized


def test_evaluate_results_calculates_recall_mrr_and_retriever_contributions():
    manifest = load_rag_manifest(FIXTURE_DIR)
    results = _passing_results(manifest, retrievers=("bm25",))
    irrelevant = {
        "corpus_chunk_id": "unrelated",
        "title": "unrelated.pdf",
        "content": "irrelevant",
        "retrievers": ["vector"],
    }
    results[manifest["queries"][0]["id"]].insert(0, irrelevant)
    results[manifest["queries"][1]["id"]][:0] = [irrelevant, irrelevant]
    results[manifest["queries"][2]["id"]][0]["retrievers"] = ["vector", "bm25"]

    report = evaluate_results(manifest, results)

    assert report["summary"]["recall_at_k"] == 1.0
    assert report["summary"]["mrr"] == pytest.approx(65 / 72)
    assert report["summary"]["provenance_accuracy"] == 1.0
    assert report["summary"]["gate"] == "passed"
    assert report["retriever_contributions"] == {
        "bm25_query_hits": 12,
        "vector_query_hits": 1,
    }


def test_evaluate_results_fails_gate_for_wrong_persisted_provenance():
    manifest = load_rag_manifest(FIXTURE_DIR)
    results = _passing_results(manifest)
    failed_query = manifest["queries"][0]
    results[failed_query["id"]] = [
        _result_for(failed_query, page_start=0, page_end=3, section_path=["wrong"])
    ]

    report = evaluate_results(manifest, results)

    assert report["summary"]["recall_at_k"] == 1.0
    assert report["summary"]["provenance_accuracy"] == pytest.approx(11 / 12)
    assert report["summary"]["gate"] == "failed"
    assert report["failed_query_ids"] == [failed_query["id"]]


def test_evaluate_results_accepts_valid_cross_page_chunk():
    manifest = load_rag_manifest(FIXTURE_DIR)
    query = next(
        query for query in manifest["queries"] if query["id"] == "annual-leave-application"
    )

    report = evaluate_results(
        {**manifest, "queries": [query]},
        {query["id"]: [_result_for(query, page_start=1, page_end=3)]},
    )

    assert report["summary"]["provenance_accuracy"] == 1.0
    assert report["summary"]["gate"] == "passed"


@pytest.mark.parametrize(
    ("query_id", "overrides"),
    [
        ("annual-leave-ten-years", {"page_start": 1, "page_end": 3}),
        ("employment-certificate", {"page_start": 1, "page_end": 1}),
    ],
)
def test_evaluate_results_rejects_out_of_document_or_invented_pages(query_id, overrides):
    manifest = load_rag_manifest(FIXTURE_DIR)
    query = next(query for query in manifest["queries"] if query["id"] == query_id)

    report = evaluate_results(
        {**manifest, "queries": [query]},
        {query["id"]: [_result_for(query, **overrides)]},
    )

    assert report["summary"]["recall_at_k"] == 1.0
    assert report["summary"]["provenance_accuracy"] == 0.0
    assert report["summary"]["gate"] == "failed"


def test_evaluate_results_keeps_one_sanitized_row_per_query_without_hits():
    manifest = load_rag_manifest(FIXTURE_DIR)

    report = evaluate_results(manifest, {})

    assert len(report["results"]) == 12
    assert all(item["rank"] is None for item in report["results"])
    assert all(item["retrievers"] == [] for item in report["results"])
    assert report["retriever_contributions"] == {
        "bm25_query_hits": 0,
        "vector_query_hits": 0,
    }


@pytest.mark.parametrize(
    "path",
    [Path("C:/temp/rag-eval"), Path("D:/other/rag-eval")],
)
def test_run_evaluation_rejects_work_dir_outside_smartcs_devdata(path):
    with pytest.raises(ValueError, match=r"D:\\DevData\\smartcs"):
        rag_evaluation.run_evaluation(FIXTURE_DIR, path, "pytest")


@pytest.mark.parametrize(
    "label",
    ["", "a" * 65, "../prod", r"prod\\local", "sk-secret-value"],
)
def test_run_evaluation_rejects_invalid_or_secret_environment_label(d_work_dir, label):
    with pytest.raises(ValueError, match="environment-label"):
        rag_evaluation.run_evaluation(FIXTURE_DIR, d_work_dir, label)


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


def _retrieval_globals():
    import app.core.retrieval_module as retrieval_module
    from app.core.agent import tools as agent_tools

    return (
        retrieval_module._vector_store,
        retrieval_module._bm25_manager,
        retrieval_module._embedding_provider,
        agent_tools._runtime.get(),
    )


def test_run_evaluation_uses_governed_documents_real_tool_and_stable_chunk_mapping(
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
    assert report["corpus"]["indexed_chunk_count"] == 11
    assert set(report["run_context"]["manifest_sha256"]) == {
        "manifest",
        "rag_manifest",
        "rag_corpus",
        "combined",
    }
    assert observed["governance_checked"] is True
    assert len(observed["queries"]) == report["query_count"] == 12
    assert report["summary"] == {
        "recall_at_k": pytest.approx(11 / 12),
        "mrr": pytest.approx(11 / 12),
        "provenance_accuracy": 1.0,
        "gate": "passed",
    }
    assert report["failed_query_ids"] == ["payroll-contact"]
    assert report["retriever_contributions"] == {
        "bm25_query_hits": 11,
        "vector_query_hits": 0,
    }
    assert report["limitations"] == {
        "deterministic_hash_embedding_is_non_semantic": True,
        "metric_scope": "curated-corpus-source-chunk-retrieval",
    }

    run_dirs = list(d_work_dir.iterdir())
    assert len(run_dirs) == 1
    database_path = run_dirs[0] / "evaluation.db"
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    session = sessionmaker(bind=engine)()
    try:
        assert session.query(DocumentFamily).count() == 8
        assert session.query(Document).count() == 8
        assert session.query(DocumentChunk).count() == 11
    finally:
        session.close()
        engine.dispose()

    serialized = json.dumps(report, ensure_ascii=False)
    assert "工龄满十年的员工每年享有十天年假。" not in serialized
    assert "sk-secret-value" not in serialized
    assert str(FIXTURE_DIR.resolve()) not in serialized
    assert str(d_work_dir.resolve()) not in serialized


def test_run_evaluation_restores_globals_and_closes_files_after_search_failure(
    d_work_dir, monkeypatch,
):
    from app.core.agent import tools as agent_tools

    before = _retrieval_globals()

    class FailingSearchTool:
        async def ainvoke(self, _payload):
            raise RuntimeError("search failed")

    monkeypatch.setattr(agent_tools, "search_knowledge", FailingSearchTool())

    with pytest.raises(RuntimeError, match="search failed"):
        rag_evaluation.run_evaluation(FIXTURE_DIR, d_work_dir, "pytest")

    assert _retrieval_globals() == before
    shutil.rmtree(d_work_dir)
    assert not d_work_dir.exists()


def test_run_evaluation_restores_globals_when_bm25_cleanup_fails(d_work_dir, monkeypatch):
    from app.core.retrieval.bm25_index import BM25IndexManager

    before = _retrieval_globals()

    def fail_cleanup(self, tenant_slug):
        raise RuntimeError(f"cleanup failed for {tenant_slug}")

    monkeypatch.setattr(BM25IndexManager, "remove_tenant", fail_cleanup)

    with pytest.raises(RuntimeError, match="cleanup failed"):
        rag_evaluation.run_evaluation(FIXTURE_DIR, d_work_dir, "pytest")

    assert _retrieval_globals() == before
    shutil.rmtree(d_work_dir)
    assert not d_work_dir.exists()


def test_cli_rejects_output_outside_smartcs_devdata(d_work_dir, tmp_path):
    with pytest.raises(ValueError, match=r"D:\\DevData\\smartcs"):
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
