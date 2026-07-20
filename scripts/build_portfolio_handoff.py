"""Build neutral, traceable SmartCS portfolio materials from an E1 manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


SENSITIVE_KEY_PARTS = (
    "api_key",
    "access_token",
    "authorization",
    "bearer",
    "password",
    "jwt_secret",
    "storage_key",
    "cookie",
)
LOCAL_PATH_PATTERN = re.compile(r"(?:[A-Za-z]:[\\/]|/Users/|\\Users\\)")
CITATION_PATTERN = re.compile(r"\[source:([^\]]+)\]")


def _walk(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def validate_manifest(manifest: dict, package_root: Path) -> None:
    if manifest.get("schema_version") != 1 or manifest.get("stage") != "E1":
        raise ValueError("unsupported evidence manifest")
    if manifest.get("status") != "complete":
        raise ValueError("E1 evidence is incomplete")
    if manifest.get("data_classification") != "public fictional demo":
        raise ValueError("evidence is not classified for public demo use")

    for key, value in _walk(manifest):
        normalized = str(key).lower()
        if any(part in normalized for part in SENSITIVE_KEY_PARTS):
            raise ValueError(f"sensitive field is forbidden: {key}")
        if isinstance(value, str) and LOCAL_PATH_PATTERN.search(value):
            raise ValueError("local path is forbidden in public evidence")

    cited = manifest.get("demo", {}).get("cited_answer", {})
    source_ids = {
        str(source.get("source_id"))
        for source in cited.get("sources") or []
        if source.get("source_id")
    }
    citation_ids = set(CITATION_PATTERN.findall(str(cited.get("reply") or "")))
    if cited.get("status") != "cited" or not citation_ids or not citation_ids <= source_ids:
        raise ValueError("citation tokens must reference authorized sources")

    demo = manifest.get("demo", {})
    if demo.get("handoff_statuses") != ["open", "assigned", "resolved", "resolved"]:
        raise ValueError("handoff lifecycle evidence is incomplete")
    retrieval = manifest.get("retrieval", {})
    if retrieval.get("gate") != "passed" or retrieval.get("provenance_accuracy") != 1.0:
        raise ValueError("retrieval evidence gate did not pass")

    root = Path(package_root).resolve()
    hashes = manifest.get("source_sha256") or {}
    if not hashes:
        raise ValueError("source hashes are required")
    for relative_path, expected_hash in hashes.items():
        source = (root / relative_path).resolve()
        if not source.is_relative_to(root) or not source.is_file():
            raise ValueError("evidence source is missing")
        actual_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise ValueError(f"evidence hash mismatch: {relative_path}")


def _percent(value: float) -> str:
    return f"{float(value) * 100:.2f}%"


def _source_ref(manifest: dict, suffix: str) -> dict:
    matches = [
        (path, digest)
        for path, digest in manifest["source_sha256"].items()
        if path.endswith(suffix)
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one evidence source ending with {suffix}")
    path, digest = matches[0]
    return {"relative_path": path, "sha256": digest}


def _manifest_ref(pointer: str, value) -> dict:
    return {"manifest_pointer": pointer, "observed_value": value}


def _build_facts(manifest: dict) -> dict:
    retrieval = manifest["retrieval"]
    tests = manifest["tests"]
    return {
        "schema_version": 1,
        "project_id": "smartcs",
        "project_name": "SmartCS",
        "positioning": "面向企业内部员工的人事知识 Agent 后端工程样板",
        "material_scope": "事实、文案和证据索引；不包含作品集前端",
        "source_commit": manifest["git_commit"],
        "captured_at_utc": manifest["captured_at_utc"],
        "data_classification": manifest["data_classification"],
        "capabilities": [
            "多租户 JWT 身份边界",
            "受治理的制度文档发布与重新索引",
            "包含授权来源标记的 RAG 回答",
            "员工确认后才提交的 HR 转人工流程",
            "固定语料检索评测与 Python 自动化回归",
        ],
        "metrics": {
            "corpus_type": "fixed curated corpus",
            "indexed_fixtures": retrieval["indexed_fixture_count"],
            "indexed_chunks": retrieval["indexed_chunk_count"],
            "query_count": retrieval["query_count"],
            "top_k": retrieval["top_k"],
            "recall_at_3": retrieval["recall_at_k"],
            "mrr": retrieval["mrr"],
            "recalled_source_provenance_accuracy": retrieval["provenance_accuracy"],
            "bm25_query_hits": retrieval["retriever_contributions"]["bm25_query_hits"],
            "vector_query_hits": retrieval["retriever_contributions"]["vector_query_hits"],
            "retained_failure": retrieval["failed_query_ids"],
        },
        "regression": {
            "passed": tests["passed"],
            "skipped": tests["skipped"],
            "warnings": tests["warnings"],
            "duration": tests["duration"],
        },
        "limitations": manifest["limitations"],
    }


def _build_claims(manifest: dict) -> dict:
    demo = manifest["demo"]
    retrieval = manifest["retrieval"]
    tests = manifest["tests"]
    demo_source = _source_ref(manifest, "demo.stdout.txt")
    rag_source = _source_ref(manifest, "rag-evaluation.json")
    pytest_source = _source_ref(manifest, "pytest.stdout.txt")

    claims = [
        {
            "id": "SC-C01",
            "title": "租户边界由后端执行",
            "claim": "跨租户 HR 数据请求返回 403 tenant_access_denied。",
            "business_value": "企业知识与员工请求不会只依赖模型提示词进行隔离。",
            "evidence": [_manifest_ref("demo.tenant_isolation", demo["tenant_isolation"]), demo_source],
            "limitation": "该证据证明应用 API 边界，不代表已经接入企业 SSO。",
        },
        {
            "id": "SC-C02",
            "title": "知识先审核再生效",
            "claim": "上传快照先处于 ready + pending_review，审核后才成为 approved + current。",
            "business_value": "为企业制度的暴露时机提供显式状态门禁。",
            "evidence": [
                _manifest_ref("demo.upload.review_status", demo["upload"]["review_status"]),
                _manifest_ref("demo.review", demo["review"]),
                _manifest_ref("demo.reindex.index_generation", demo["reindex"]["index_generation"]),
                demo_source,
            ],
            "limitation": "演示证明当前治理状态机，不等同于完整企业内容管理平台。",
        },
        {
            "id": "SC-C03",
            "title": "回答携带授权来源",
            "claim": "年假制度回答同时返回结构化来源，并在正文中包含对应 source 标记。",
            "business_value": "员工可以追溯回答依据，展示材料也能检查 source 标记与结构化来源一致。",
            "evidence": [
                _manifest_ref("demo.cited_answer.status", demo["cited_answer"]["status"]),
                _manifest_ref("demo.cited_answer.reply", demo["cited_answer"]["reply"]),
                demo_source,
            ],
            "limitation": "这是一次公开虚构数据演示，不代表所有真实企业文档都能达到同等解析质量。",
        },
        {
            "id": "SC-C04",
            "title": "Agent 行动经过人工确认",
            "claim": "模型生成待确认草稿，员工确认后请求才进入 open，再由 HR 更新为 assigned 和 resolved。",
            "business_value": "高影响动作保留人的确认权，模型不能直接代替员工提交或结单。",
            "evidence": [
                _manifest_ref("demo.handoff_statuses", demo["handoff_statuses"]),
                demo_source,
            ],
            "limitation": "当前是 HR 转人工闭环，不是完整请假审批或 HRIS 集成。",
        },
        {
            "id": "SC-C05",
            "title": "检索质量有固定回归集",
            "claim": (
                f"固定语料 12 条问题的 Recall@3 和 MRR 均为 {_percent(retrieval['recall_at_k'])}，"
                f"保留失败问题 {', '.join(retrieval['failed_query_ids'])}。"
            ),
            "business_value": "RAG 改动可以对照同一批问题回归，而不是只凭主观聊天体验判断。",
            "evidence": [
                _manifest_ref("retrieval", retrieval),
                rag_source,
            ],
            "limitation": "这是 curated corpus 离线结果；HashEmbedding 非语义，vector 贡献为 0，不是生产 SLA。",
        },
        {
            "id": "SC-C06",
            "title": "后端行为有自动化回归",
            "claim": f"同一 commit 的全量回归结果为 {tests['passed']} passed、{tests['skipped']} skipped、0 failed。",
            "business_value": "认证、租户隔离、文档治理、检索、Agent 工具和转人工状态可重复验证。",
            "evidence": [
                _manifest_ref("tests", tests),
                pytest_source,
            ],
            "limitation": f"本次仍有 {tests['warnings']} 条已知依赖弃用警告；通过测试不等于生产可用性证明。",
        },
    ]
    return {
        "schema_version": 1,
        "source_commit": manifest["git_commit"],
        "data_classification": manifest["data_classification"],
        "claims": claims,
    }


def _build_copy(manifest: dict) -> str:
    retrieval = manifest["retrieval"]
    tests = manifest["tests"]
    recall = _percent(retrieval["recall_at_k"])
    failed = ", ".join(retrieval["failed_query_ids"])
    return f"""# SmartCS 作品集文案素材

> 这些是经过证据约束的文案原料，不是最终页面。作品集任务可以调整排版，不能改变数字、状态顺序或限制。

## 一句话定位

面向企业内部员工的人事知识 Agent 后端工程样板，覆盖受治理的制度发布、带来源问答、受控转人工和多租户身份边界。

## 项目简介

SmartCS 不是一套完整 HRIS，也不是通用聊天机器人。它聚焦企业 AI 应用中最容易被忽略的后端约束：知识何时生效、来源是否授权、Agent 能执行到哪一步、跨租户请求如何拒绝，以及 RAG 改动如何回归验证。

## 简历 Bullet

- 独立设计并实现 Python 企业人事知识 Agent 后端，将 JWT 租户身份、制度审核状态、RAG 来源引用和 HR 转人工状态机组合为一条可验证业务链路。
- 建立固定语料 RAG 回归集，12 条查询 Recall@3 / MRR 均为 {recall}，保留失败问题 `{failed}`，并明确 HashEmbedding 非语义、vector 贡献为 0 的限制。
- 为认证、租户隔离、文档治理、检索和 Agent 工具调用建立自动化回归；本次同一 commit 验证结果为 {tests['passed']} passed、{tests['skipped']} skipped、0 failed。

## 面试讲法

1. **业务问题：** 企业制度上传成功不代表应该立即被员工检索，异常问题也不能由模型直接代替员工提交。
2. **设计选择：** 用后端状态控制 `pending_review -> approved/current`，只允许当次授权检索来源进入回答，并把高影响工具调用限制为待确认草稿。
3. **权限边界：** JWT 中的租户和角色由 API 校验；跨租户 HR 数据请求直接返回 `403 tenant_access_denied`。
4. **工程验证：** 演示、检索评测和全量 pytest 在同一 Git commit 重新执行，输出经过脱敏并用 SHA-256 关联原始记录。
5. **诚实取舍：** 当前检索评测使用固定 curated corpus，HashEmbedding 不提供真实语义质量，因此指标只作为离线回归门禁，不包装成生产 SLA。

## 可展示指标

- 固定语料：{retrieval['indexed_fixture_count']} 个 fixtures、{retrieval['indexed_chunk_count']} 个 source chunks、{retrieval['query_count']} 条查询、top_k={retrieval['top_k']}。
- Recall@3：{recall}；MRR：{_percent(retrieval['mrr'])}。
- 已召回来源 provenance：{_percent(retrieval['provenance_accuracy'])}，不代表全部查询都命中。
- 检索贡献：BM25 {retrieval['retriever_contributions']['bm25_query_hits']}，vector {retrieval['retriever_contributions']['vector_query_hits']}。
- 保留失败问题：`{failed}`。
- Python 回归：{tests['passed']} passed、{tests['skipped']} skipped、{tests['warnings']} warning、0 failed。

## 禁止宣传

- 不得写成“已生产部署”“商业 HR SaaS”或“完整 HRIS”。
- 不得宣称已经接入企业 SSO、真实 HRIS 或真实员工数据。
- 不得把 provenance 100% 改写成“全部问题准确率 100%”。
- 不得把 HashEmbedding 和 vector 贡献 0 包装成高质量语义向量检索。
- 不得把整理后的证据图片称为 SmartCS 产品后台截图。
- 不得删除 curated corpus、失败问题和非生产 SLA 限制。
"""


def _build_readme(manifest: dict) -> str:
    return f"""# SmartCS 中立作品集素材包

本目录提供事实、文案和证据索引，**不是作品集前端**，也不是 SmartCS 产品界面。

## 文件

- `project-facts.json`：机器可读的定位、能力、指标和限制。
- `claims.json`：每条可展示结论、业务价值、证据位置和适用边界。
- `portfolio-copy.md`：简历 Bullet、面试讲法、指标文案和禁止宣传内容。
- `README.md`：消费规则。

## 消费规则

作品集任务可以重排、裁切或缩写文案，但必须保留 claim 的事实含义、来源 commit、公开虚构数据标签和限制。不得根据这些文件虚构产品后台、企业客户、线上规模或生产 SLA。

- 来源 commit：`{manifest['git_commit']}`
- 采集时间：`{manifest['captured_at_utc']}`
- 数据边界：`{manifest['data_classification']}`
"""


def build_handoff_package(manifest_path: Path, output_dir: Path) -> dict[str, Path]:
    manifest_path = Path(manifest_path)
    output_dir = Path(output_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_manifest(manifest, manifest_path.parent)
    output_dir.mkdir(parents=True, exist_ok=True)

    outputs = {
        "readme": output_dir / "README.md",
        "facts": output_dir / "project-facts.json",
        "claims": output_dir / "claims.json",
        "copy": output_dir / "portfolio-copy.md",
    }
    outputs["readme"].write_text(_build_readme(manifest), encoding="utf-8")
    outputs["facts"].write_text(
        json.dumps(_build_facts(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    outputs["claims"].write_text(
        json.dumps(_build_claims(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    outputs["copy"].write_text(_build_copy(manifest), encoding="utf-8")
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Build SmartCS portfolio handoff materials")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    for path in build_handoff_package(args.manifest, args.output_dir).values():
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
