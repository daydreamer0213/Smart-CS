import hashlib
import json

import pytest

from scripts.build_portfolio_handoff import build_handoff_package, validate_manifest


def _manifest(tmp_path):
    sources = {}
    for name, content in {
        "demo.stdout.txt": "safe demo evidence",
        "rag-evaluation.json": "safe retrieval evidence",
        "pytest.stdout.txt": "safe regression evidence",
    }.items():
        source = tmp_path / "raw" / "run-1" / "commands" / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(content, encoding="utf-8")
        sources[source.relative_to(tmp_path).as_posix()] = hashlib.sha256(source.read_bytes()).hexdigest()

    return {
        "schema_version": 1,
        "package": "SmartCS portfolio evidence",
        "stage": "E1",
        "status": "complete",
        "run_id": "run-1",
        "git_commit": "12c374a9a16743f6d9fe09151afdf862b7e7652d",
        "captured_at_utc": "2026-07-20T07:30:00+00:00",
        "data_classification": "public fictional demo",
        "demo": {
            "upload": {
                "version": 1,
                "index_generation": 1,
                "review_status": "pending_review",
                "status": "ready",
            },
            "review": {"review_status": "approved", "is_current": True},
            "cited_answer": {
                "reply": "年假为 5 个工作日。[source:source-1]",
                "sources": [{
                    "source_type": "document",
                    "source_id": "source-1",
                    "title": "Annual Leave Policy",
                }],
                "status": "cited",
            },
            "reindex": {"index_generation": 2, "status": "ready", "is_current": True},
            "handoff_statuses": ["open", "assigned", "resolved", "resolved"],
            "tenant_isolation": "403 tenant_access_denied",
        },
        "retrieval": {
            "indexed_fixture_count": 8,
            "indexed_chunk_count": 11,
            "query_count": 12,
            "top_k": 3,
            "recall_at_k": 0.9166666666666666,
            "mrr": 0.9166666666666666,
            "provenance_accuracy": 1.0,
            "gate": "passed",
            "failed_query_ids": ["payroll-contact"],
            "retriever_contributions": {"bm25_query_hits": 11, "vector_query_hits": 0},
        },
        "tests": {"passed": 396, "skipped": 4, "warnings": 1, "duration": "61.51s"},
        "limitations": [
            "Retrieval metrics come from a fixed curated corpus and are not a production SLA.",
            "HashEmbedding is non-semantic; BM25 contributed 11 query hits and vector retrieval contributed 0.",
        ],
        "source_sha256": sources,
    }


def test_validate_manifest_rejects_unsafe_or_changed_evidence(tmp_path):
    manifest = _manifest(tmp_path)
    manifest["demo"]["cited_answer"]["reply"] = "错误引用 [source:other-source]"
    with pytest.raises(ValueError, match="citation"):
        validate_manifest(manifest, tmp_path)

    manifest = _manifest(tmp_path)
    source = tmp_path / next(iter(manifest["source_sha256"]))
    source.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        validate_manifest(manifest, tmp_path)

    manifest = _manifest(tmp_path)
    manifest["demo"]["access_token"] = "secret"
    with pytest.raises(ValueError, match="sensitive"):
        validate_manifest(manifest, tmp_path)


def test_build_handoff_outputs_neutral_traceable_materials(tmp_path):
    manifest = _manifest(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    output_dir = tmp_path / "materials"

    outputs = build_handoff_package(manifest_path, output_dir)

    assert set(outputs) == {"readme", "facts", "claims", "copy"}
    assert {path.name for path in output_dir.iterdir()} == {
        "README.md",
        "project-facts.json",
        "claims.json",
        "portfolio-copy.md",
    }

    facts = json.loads((output_dir / "project-facts.json").read_text(encoding="utf-8"))
    claims = json.loads((output_dir / "claims.json").read_text(encoding="utf-8"))
    copy = (output_dir / "portfolio-copy.md").read_text(encoding="utf-8")
    readme = (output_dir / "README.md").read_text(encoding="utf-8")

    assert facts["source_commit"] == manifest["git_commit"]
    assert facts["data_classification"] == "public fictional demo"
    assert facts["metrics"]["recall_at_3"] == 0.9166666666666666
    assert facts["regression"]["passed"] == 396
    assert len(claims["claims"]) == 6
    assert all(claim["evidence"] for claim in claims["claims"])
    assert all(ref.get("manifest_pointer") or ref.get("relative_path") for claim in claims["claims"] for ref in claim["evidence"])
    assert "不是作品集前端" in readme
    assert "简历 Bullet" in copy
    assert "面试讲法" in copy
    assert "禁止宣传" in copy
    assert "91.67%" in copy
    assert "payroll-contact" in copy

    rendered = "\n".join(path.read_text(encoding="utf-8") for path in output_dir.iterdir())
    assert "<html" not in rendered.lower()
    assert "<style" not in rendered.lower()
    assert "C:\\Users" not in rendered
    assert "D:\\" not in rendered
