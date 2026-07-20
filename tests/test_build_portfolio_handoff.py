import hashlib
import json

import pytest

from scripts.build_portfolio_handoff import (
    _validate_generated_outputs,
    build_handoff_package,
    validate_manifest,
)


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

    assert set(outputs) == {"readme", "facts", "claims", "copy", "modules", "guide", "handoff"}
    assert {path.name for path in output_dir.iterdir()} == {
        "README.md",
        "project-facts.json",
        "claims.json",
        "portfolio-copy.md",
        "portfolio-modules.json",
        "portfolio-modules.md",
    }
    assert outputs["handoff"] == tmp_path / "handoff.json"
    assert outputs["handoff"].is_file()

    facts = json.loads((output_dir / "project-facts.json").read_text(encoding="utf-8"))
    claims = json.loads((output_dir / "claims.json").read_text(encoding="utf-8"))
    copy = (output_dir / "portfolio-copy.md").read_text(encoding="utf-8")
    modules = json.loads((output_dir / "portfolio-modules.json").read_text(encoding="utf-8"))
    guide = (output_dir / "portfolio-modules.md").read_text(encoding="utf-8")
    handoff = json.loads(outputs["handoff"].read_text(encoding="utf-8"))
    readme = (output_dir / "README.md").read_text(encoding="utf-8")

    assert facts["source_commit"] == manifest["git_commit"]
    assert facts["data_classification"] == "public fictional demo"
    assert facts["metrics"]["recall_at_3"] == 0.9166666666666666
    assert facts["regression"]["passed"] == 396
    assert len(claims["claims"]) == 6
    assert all(claim["evidence"] for claim in claims["claims"])
    assert all(ref.get("manifest_pointer") or ref.get("relative_path") for claim in claims["claims"] for ref in claim["evidence"])
    assert "不包含作品集前端" in readme
    assert "简历 Bullet" in copy
    assert "面试讲法" in copy
    assert "禁止宣传" in copy
    assert "91.67%" in copy
    assert "payroll-contact" in copy
    assert [module["id"] for module in modules["modules"]] == [
        "overview",
        "knowledge-governance",
        "agent-boundary",
        "engineering-quality",
    ]
    claim_ids = {claim["id"] for claim in claims["claims"]}
    for order, module in enumerate(modules["modules"], start=1):
        assert module["order"] == order
        assert module["title"]
        assert module["summary"]
        assert module["claim_ids"]
        assert set(module["claim_ids"]) <= claim_ids
        assert module["proof_items"]
        assert all(item["claim_id"] in module["claim_ids"] for item in module["proof_items"])
        assert module["layout"]["desktop"]
        assert module["layout"]["mobile"]
        assert module["alt_text"]
        assert module["limitation"]

    overview_steps = modules["modules"][0]["workflow_steps"]
    assert [step["id"] for step in overview_steps] == [
        "upload",
        "review",
        "ask",
        "cite",
        "handoff",
    ]
    assert all(step["label"] and step["text"] for step in overview_steps)
    assert all(step["claim_id"] in modules["modules"][0]["claim_ids"] for step in overview_steps)

    page_copy = "\n".join(
        [module["title"] for module in modules["modules"]]
        + [module["summary"] for module in modules["modules"]]
        + [item["text"] for module in modules["modules"] for item in module["proof_items"]]
    )
    for template_phrase in ("不是", "而不是", "真正的问题", "不能只"):
        assert template_phrase not in page_copy

    assert handoff["status"] == "ready"
    assert handoff["target_task_id"] == "019f59c1-a1ab-7820-a310-ff2365afaee8"
    assert handoff["source_commit"] == manifest["git_commit"]
    assert handoff["data_classification"] == "public fictional demo"
    assert handoff["module_order"] == [module["id"] for module in modules["modules"]]
    assert handoff["frontend_owner"] == "portfolio task"
    assert handoff["asset_policy"]["archived_video_included"] is False
    assert handoff["handoff_status_semantics"] == {
        "transitions": ["open", "assigned", "resolved"],
        "employee_observation": "resolved",
    }
    assert handoff["files"] == {
        "facts": "materials/project-facts.json",
        "claims": "materials/claims.json",
        "copy": "materials/portfolio-copy.md",
        "modules": "materials/portfolio-modules.json",
        "integration_guide": "materials/portfolio-modules.md",
    }
    assert handoff["prohibited_claims"] == [
        "已生产部署",
        "商业 HR SaaS",
        "完整 HRIS",
        "已接入企业 SSO",
        "已接入真实 HRIS 或真实员工数据",
        "生产 SLA",
        "高质量语义向量检索",
        "全部问题准确率 100%",
        "完整请假审批",
        "产品后台截图",
    ]
    assert set(handoff["evidence_catalog"]) == {"demo_stdout", "rag_report", "pytest_stdout"}
    assert all(item["relative_path"] and item["sha256"] for item in handoff["evidence_catalog"].values())
    assert "四个模块" in guide
    assert "375px" in guide
    assert "归档视频" in guide

    rendered = "\n".join(path.read_text(encoding="utf-8") for path in output_dir.iterdir()) + outputs["handoff"].read_text(encoding="utf-8")
    assert "<html" not in rendered.lower()
    assert "<style" not in rendered.lower()
    assert "C:\\Users" not in rendered
    assert "D:\\" not in rendered
    assert "SC-05.mp4" not in rendered
    assert "\ufffd" not in rendered
    for template_phrase in ("不是", "而不是", "真正的问题", "不能只"):
        assert template_phrase not in rendered


def test_build_handoff_requires_the_materials_package_layout(tmp_path):
    manifest = _manifest(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="materials"):
        build_handoff_package(manifest_path, tmp_path / "arbitrary-output")


def test_generated_output_safety_scan_rejects_private_or_media_content(tmp_path):
    output = tmp_path / "output.txt"
    unsafe_values = [
        r"C:\temp\private.txt",
        r"\\server\share\private.txt",
        "/home/user/private.txt",
        "/etc/private.conf",
        "/opt/private/data",
        "/mnt/private/data",
        "/srv/evidence/run.txt",
        "/data/raw/demo.stdout.txt",
        "/Volumes/SSD/archive.mov",
        r"\Windows\private.ini",
        "SC-05.webm",
        "<html><body>unexpected page</body></html>",
        '"api_key": "secret"',
        '"client_secret": "secret"',
        '"private_key": "secret"',
        '"refresh_token": "secret"',
        "Bearer secret-token",
        "-----BEGIN PRIVATE KEY-----",
        "broken \ufffd text",
    ]

    for unsafe in unsafe_values:
        output.write_text(unsafe, encoding="utf-8")
        with pytest.raises(ValueError, match="generated output"):
            _validate_generated_outputs({"sample": output})

    for safe in (
        "Password Policy",
        "cookie preference text",
        "public-policy.webp",
        "https://example.com/public-policy.webp",
        "HTML/CSS",
        "Recall@3 / MRR",
    ):
        output.write_text(safe, encoding="utf-8")
        _validate_generated_outputs({"sample": output})


def test_unsafe_generated_content_is_rejected_before_writing(tmp_path):
    manifest = _manifest(tmp_path)
    manifest["limitations"].append("SC-05.webm")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    output_dir = tmp_path / "materials"

    with pytest.raises(ValueError, match="generated output"):
        build_handoff_package(manifest_path, output_dir)

    assert not output_dir.exists()
    assert not (tmp_path / "handoff.json").exists()
