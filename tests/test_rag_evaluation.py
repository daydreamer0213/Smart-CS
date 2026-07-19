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
from app.core.parsing.contracts import ParsedDocument, ParsedElement
from app.models.document import Document, DocumentFamily
from scripts.evaluate_rag_retrieval import evaluate_results, load_rag_manifest


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "documents"


@pytest.fixture
def d_work_dir():
    path = Path("D:/DevData/smartcs/pytest-rag-eval") / uuid.uuid4().hex
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def lightweight_parser(monkeypatch):
    document_manifest = json.loads(
        (FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8")
    )
    fixtures = {item["filename"]: item for item in document_manifest["fixtures"]}
    parsed_filenames = []

    def parse(source_path, _expected_route, _run_dir):
        filename = source_path.name
        parsed_filenames.append(filename)
        fixture = fixtures[filename]
        elements = [
            ParsedElement(
                text=item["fact"],
                element_type="paragraph",
                page_start=item["page_start"],
                page_end=item["page_end"],
                section_path=item["section_path"],
            )
            for item in fixture["expected_fact_provenance"]
        ]
        if filename == "clean_policy.pdf":
            elements[0].text += " SENSITIVE_CHUNK_BODY sk-secret-value C:\\private"
        page_count = max(
            (item.page_end or 0 for item in elements),
            default=0,
        )
        covered_pages = {
            page
            for item in elements
            if item.page_start is not None and item.page_end is not None
            for page in range(item.page_start, item.page_end + 1)
        }
        elements.extend(
            ParsedElement(
                text=f"第 {page} 页测试内容。",
                element_type="paragraph",
                page_start=page,
                page_end=page,
            )
            for page in range(1, page_count + 1)
            if page not in covered_pages
        )
        return ParsedDocument(
            parser_name="test-parser",
            parser_version="1",
            page_count=page_count,
            elements=elements,
        )

    monkeypatch.setattr(rag_evaluation, "parse_fixture", parse)
    return parsed_filenames


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


def test_parse_fixture_uses_lightweight_subprocess_for_advanced_route(tmp_path, monkeypatch):
    parsed = ParsedDocument(
        parser_name="worker-parser",
        parser_version="1",
        page_count=1,
        elements=[ParsedElement(text="advanced", element_type="paragraph", page_start=1)],
    )
    observed = []
    source = tmp_path / "advanced.pdf"
    source.write_bytes(b"pdf")
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    def run(command, *, check):
        observed.append((command, check))
        Path(command[-1]).write_text(parsed.model_dump_json(), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(rag_evaluation.subprocess, "run", run)
    monkeypatch.setattr(
        rag_evaluation,
        "parse_structured_file",
        lambda *_args: pytest.fail("advanced parsing must not run in the parent process"),
    )

    actual = rag_evaluation.parse_fixture(source, "advanced", run_dir)

    assert actual.model_dump() == parsed.model_dump()
    assert observed == [(
        [
            sys.executable,
            str(rag_evaluation.LIGHTWEIGHT_PARSER_WORKER),
            str(source),
            str(run_dir / "advanced.json"),
        ],
        True,
    )]
    assert not (run_dir / "advanced.json").exists()


def test_parse_fixture_keeps_native_route_in_current_process(tmp_path, monkeypatch):
    parsed = ParsedDocument(
        parser_name="native-parser",
        parser_version="1",
        page_count=1,
        elements=[ParsedElement(text="native", element_type="paragraph", page_start=1)],
    )
    observed = []
    source = tmp_path / "native.pdf"
    source.write_bytes(b"pdf")
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    def parse(filename, data):
        observed.append(("parent", filename, data))
        return parsed

    monkeypatch.setattr(rag_evaluation, "parse_structured_file", parse)
    monkeypatch.setattr(
        rag_evaluation,
        "subprocess",
        pytest.fail,
    )

    actual = rag_evaluation.parse_fixture(source, "native", run_dir)

    assert actual is parsed
    assert observed == [("parent", "native.pdf", b"pdf")]


def test_parse_fixture_propagates_lightweight_subprocess_failure_and_cleans_output(tmp_path, monkeypatch):
    source = tmp_path / "advanced.pdf"
    source.write_bytes(b"pdf")
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    def run(command, *, check):
        Path(command[-1]).write_text("partial", encoding="utf-8")
        raise subprocess.CalledProcessError(2, command)

    monkeypatch.setattr(rag_evaluation.subprocess, "run", run)

    with pytest.raises(subprocess.CalledProcessError):
        rag_evaluation.parse_fixture(source, "advanced", run_dir)

    assert not (run_dir / "advanced.json").exists()


def test_run_evaluation_releases_sqlite_when_parsing_fails(d_work_dir, monkeypatch):
    monkeypatch.setattr(
        rag_evaluation,
        "parse_fixture",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("parse failed")),
    )

    with pytest.raises(RuntimeError, match="parse failed"):
        rag_evaluation.run_evaluation(FIXTURE_DIR, d_work_dir, "pytest")

    shutil.rmtree(d_work_dir)
    assert not d_work_dir.exists()


def test_run_evaluation_uses_governed_documents_and_real_tool_boundary(
    d_work_dir, lightweight_parser, monkeypatch,
):
    original_tool = rag_evaluation.search_knowledge
    observed = {"queries": [], "governance_checked": False}

    class SearchToolSpy:
        async def ainvoke(self, payload):
            observed["queries"].append(payload["query"])
            runtime = rag_evaluation._agent_runtime.get()
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

    monkeypatch.setattr(rag_evaluation, "search_knowledge", SearchToolSpy())

    report = rag_evaluation.run_evaluation(FIXTURE_DIR, d_work_dir, "pytest")

    assert "encrypted_policy.pdf" not in lightweight_parser
    assert report["corpus"]["excluded_fixture_ids"] == ["encrypted-policy"]
    assert report["corpus"]["indexed_fixture_count"] == 8
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
    assert "SENSITIVE_CHUNK_BODY" not in serialized
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
