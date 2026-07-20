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
LOCAL_PATH_PATTERN = re.compile(
    r"(?:"
    r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]+"
    r"|\\{2,}[^\\/\s]+[\\/]+"
    r"|(?<![\w:/.])/(?!/)(?:[^\s/]+/)*[^\s/]+"
    r"|\\+(?:Users|Windows|Program Files|ProgramData)(?:[\\/]|\b)"
    r")",
    re.IGNORECASE,
)
CITATION_PATTERN = re.compile(r"\[source:([^\]]+)\]")
GENERATED_SENSITIVE_FIELD_PATTERN = re.compile(
    r"(?:[\"']?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|"
    r"private[_-]?key|authorization|password|jwt[_-]?secret|storage[_-]?key|cookie)"
    r"[\"']?\s*[:=])",
    re.IGNORECASE,
)
GENERATED_SECRET_VALUE_PATTERN = re.compile(
    r"(?:sk-[A-Za-z0-9._-]{8,}|Bearer\s+\S+|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)",
    re.IGNORECASE,
)
GENERATED_ARCHIVED_MEDIA_PATTERN = re.compile(
    r"(?:\bSC-05(?:-[^\s\"'<>]*)?\.(?:mp4|webm|mov|mkv|srt|vtt|webp|png|jpe?g)\b"
    r"|archive[\\/]2026-07-20-sc-05-video\b"
    r"|exports[\\/]keyframes\b"
    r"|masters[\\/]SC-05\b)",
    re.IGNORECASE,
)
GENERATED_MARKUP_PATTERN = re.compile(r"(?i)<(?:html|style)\b")
GENERATED_TEMPLATE_PHRASES = ("不是", "而不是", "真正的问题", "不能只")


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


def _validate_generated_texts(contents: dict[str, str]) -> None:
    for label, text in contents.items():
        if "\ufffd" in text:
            raise ValueError(f"generated output contains replacement characters: {label}")
        if LOCAL_PATH_PATTERN.search(text):
            raise ValueError(f"generated output contains a local path: {label}")
        if GENERATED_SENSITIVE_FIELD_PATTERN.search(text) or GENERATED_SECRET_VALUE_PATTERN.search(text):
            raise ValueError(f"generated output contains a sensitive term: {label}")
        if GENERATED_ARCHIVED_MEDIA_PATTERN.search(text):
            raise ValueError(f"generated output contains an archived media reference: {label}")
        if GENERATED_MARKUP_PATTERN.search(text):
            raise ValueError(f"generated output contains frontend markup: {label}")
        if any(phrase in text for phrase in GENERATED_TEMPLATE_PHRASES):
            raise ValueError(f"generated output contains contrast-formula copy: {label}")


def _validate_generated_outputs(outputs: dict[str, Path]) -> None:
    _validate_generated_texts(
        {label: Path(path).read_text(encoding="utf-8") for label, path in outputs.items()}
    )


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
                _manifest_ref("demo.cited_answer.sources", demo["cited_answer"]["sources"]),
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
            "limitation": "当前范围为 HR 转人工闭环；请假审批和 HRIS 集成尚未实现。",
        },
        {
            "id": "SC-C05",
            "title": "检索质量有固定回归集",
            "claim": (
                f"固定语料 12 条问题的 Recall@3 和 MRR 均为 {_percent(retrieval['recall_at_k'])}，"
                f"保留失败问题 {', '.join(retrieval['failed_query_ids'])}。"
            ),
            "business_value": "同一批问题为 RAG 改动提供可重复比较基线。",
            "evidence": [
                _manifest_ref("retrieval", retrieval),
                rag_source,
            ],
            "limitation": "指标来自 curated corpus 离线评测；HashEmbedding 非语义，vector 贡献为 0；当前没有生产 SLA 数据。",
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


def _build_modules(manifest: dict) -> dict:
    demo = manifest["demo"]
    retrieval = manifest["retrieval"]
    tests = manifest["tests"]
    recall = _percent(retrieval["recall_at_k"])
    mrr = _percent(retrieval["mrr"])
    provenance = _percent(retrieval["provenance_accuracy"])
    failed = ", ".join(retrieval["failed_query_ids"])

    return {
        "schema_version": 1,
        "project_id": "smartcs",
        "source_commit": manifest["git_commit"],
        "data_classification": manifest["data_classification"],
        "presentation": {
            "format": "four responsive content modules",
            "frontend_owner": "portfolio task",
            "archived_video_included": False,
        },
        "copy_style": {
            "tone": "direct factual engineering copy",
            "avoid": ["contrast-formula slogans", "unsupported superlatives", "marketing claims"],
        },
        "modules": [
            {
                "id": "overview",
                "order": 1,
                "eyebrow": "项目概览",
                "title": "SmartCS 企业人事知识 Agent",
                "summary": "在一个 Python 后端中实现制度文档治理、带来源 RAG 问答、受控人工转办和租户隔离。",
                "claim_ids": ["SC-C01", "SC-C02", "SC-C03", "SC-C04"],
                "proof_items": [
                    {"label": "隔离", "text": "跨租户 HR 请求返回 403 tenant_access_denied。", "claim_id": "SC-C01"},
                    {"label": "知识", "text": "制度快照经过审核后成为 current 版本。", "claim_id": "SC-C02"},
                    {"label": "回答", "text": "正文来源标记可与结构化 sources 相互核对。", "claim_id": "SC-C03"},
                    {"label": "行动", "text": "员工确认后，请求才进入正式 HR 转办流程。", "claim_id": "SC-C04"},
                ],
                "workflow_steps": [
                    {"id": "upload", "label": "上传制度", "text": "新快照进入待审核状态。", "claim_id": "SC-C02"},
                    {"id": "review", "label": "审核发布", "text": "审核通过后切换为 current。", "claim_id": "SC-C02"},
                    {"id": "ask", "label": "员工提问", "text": "员工问题进入知识检索链路。", "claim_id": "SC-C03"},
                    {"id": "cite", "label": "来源回答", "text": "回答同时返回正文标记和结构化来源。", "claim_id": "SC-C03"},
                    {"id": "handoff", "label": "例外转办", "text": "员工确认后创建正式 HR 请求。", "claim_id": "SC-C04"},
                ],
                "layout": {
                    "desktop": "左侧项目定位，右侧四项工程证据；下方使用五步处理链。",
                    "mobile": "单列显示定位、证据和五步处理链；每一步独占一行。",
                },
                "alt_text": "SmartCS 项目概览，展示租户身份、知识治理、带来源回答和人工转办四项能力。",
                "limitation": "公开虚构数据的工程样板，尚未接入企业 SSO 和真实 HRIS。",
            },
            {
                "id": "knowledge-governance",
                "order": 2,
                "eyebrow": "知识治理与引用",
                "title": "制度审核后生效，回答保留来源",
                "summary": "上传快照先进入待审核状态；审核通过后发布为 current，员工问答同时返回正文来源标记和结构化来源。",
                "claim_ids": ["SC-C02", "SC-C03"],
                "proof_items": [
                    {"label": "上传", "text": "ready + pending_review，version 1，index_generation 1。", "claim_id": "SC-C02"},
                    {"label": "发布", "text": "approved + current；重新索引成功后切换到 generation 2。", "claim_id": "SC-C02"},
                    {"label": "引用", "text": "回答中的 source ID 与结构化来源 ID 一致。", "claim_id": "SC-C03"},
                ],
                "sample_answer": {
                    "reply": demo["cited_answer"]["reply"],
                    "sources": demo["cited_answer"]["sources"],
                },
                "layout": {
                    "desktop": "左侧显示发布状态链，右侧显示问答节选和来源条目。",
                    "mobile": "先显示状态链，再显示回答与来源；长 source ID 允许换行。",
                },
                "alt_text": "制度文档从待审核到发布的状态变化，以及带结构化来源的员工年假回答。",
                "limitation": "证据来自一次公开虚构数据演示，真实企业文档解析质量需要独立验证。",
            },
            {
                "id": "agent-boundary",
                "order": 3,
                "eyebrow": "Agent 行动与权限",
                "title": "员工确认后提交，租户边界由 API 执行",
                "summary": "模型生成待确认草稿；员工确认后进入 open，HR 再将请求更新为 assigned 和 resolved。",
                "claim_ids": ["SC-C04", "SC-C01"],
                "proof_items": [
                    {"label": "草稿", "text": "Agent 生成 pending 草稿。", "claim_id": "SC-C04"},
                    {"label": "提交", "text": "员工确认后创建 open 请求。", "claim_id": "SC-C04"},
                    {"label": "处理", "text": "HR 将请求更新为 assigned 和 resolved。", "claim_id": "SC-C04"},
                    {"label": "隔离", "text": "跨租户 HR 数据请求返回 403 tenant_access_denied。", "claim_id": "SC-C01"},
                ],
                "layout": {
                    "desktop": "使用横向状态链展示四个动作节点，403 证据放在同一区域右侧。",
                    "mobile": "状态链改为纵向，403 证据紧随流程，不使用横向滚动。",
                },
                "alt_text": "Agent 草稿经员工确认后进入 HR 处理，并展示跨租户请求被 API 拒绝。",
                "limitation": "当前覆盖 HR 转人工闭环，尚未实现请假审批和 HRIS 集成。",
            },
            {
                "id": "engineering-quality",
                "order": 4,
                "eyebrow": "工程质量",
                "title": "固定评测集与自动化回归",
                "summary": "固定语料记录检索指标、失败问题和检索器贡献；同一证据提交保留完整 pytest 结果。",
                "claim_ids": ["SC-C05", "SC-C06"],
                "proof_items": [
                    {"label": "Recall@3", "text": recall, "claim_id": "SC-C05"},
                    {"label": "MRR", "text": mrr, "claim_id": "SC-C05"},
                    {"label": "已召回来源 provenance", "text": provenance, "claim_id": "SC-C05"},
                    {"label": "失败问题", "text": failed, "claim_id": "SC-C05"},
                    {"label": "检索贡献", "text": f"BM25 {retrieval['retriever_contributions']['bm25_query_hits']}，vector {retrieval['retriever_contributions']['vector_query_hits']}。", "claim_id": "SC-C05"},
                    {"label": "Python 回归", "text": f"{tests['passed']} passed，{tests['skipped']} skipped，0 failed，{tests['warnings']} warning。", "claim_id": "SC-C06"},
                ],
                "layout": {
                    "desktop": "上方使用三个指标块，下方并列显示检索贡献、失败问题、测试结果和限制。",
                    "mobile": "指标块单列排列；限制直接跟随指标，不放入悬浮提示。",
                },
                "alt_text": f"SmartCS 检索评测结果：Recall@3 和 MRR 为 {recall}，保留失败问题 {failed}，并展示 Python 回归结果。",
                "limitation": "指标来自固定 curated corpus；HashEmbedding 为非语义实现，vector 贡献为 0，结果不代表生产 SLA。",
            },
        ],
    }


def _build_module_guide(manifest: dict, modules: dict) -> str:
    sections = []
    for module in modules["modules"]:
        proofs = "\n".join(
            f"- **{item['label']}：** {item['text']}（{item['claim_id']}）"
            for item in module["proof_items"]
        )
        sections.append(
            f"""## {module['order']}. {module['title']}

{module['summary']}

{proofs}

- **桌面：** {module['layout']['desktop']}
- **375px 手机：** {module['layout']['mobile']}
- **替代文本：** {module['alt_text']}
- **范围说明：** {module['limitation']}
"""
        )

    return f"""# SmartCS 四模块作品集整合说明

本文件是内容与证据合同，不包含页面实现。作品集任务负责在现有视觉系统中重建四个模块。

## 整合原则

- 四个模块按固定顺序展示，桌面端可以并列，375px 手机端使用单列。
- 标题、摘要和关键证据使用 HTML 文本呈现，不把密集的 16:9 画面直接嵌入页面。
- 每个结论保留 claim ID；指标、失败问题、来源和限制始终可见。
- 来源 ID 允许换行，状态同时使用文字和颜色表达，指标提供可读的文字标签。
- 归档视频、封面、字幕和关键帧不进入正式作品集资产。
- 页面显著说明：公开虚构演示数据，不代表生产部署。

{chr(10).join(sections)}
## 验收

- 桌面端和 375px 手机端均无横向溢出。
- 四个模块的阅读与键盘焦点顺序一致。
- 数字、状态、失败问题和限制与 `portfolio-modules.json` 一致。
- 页面不显示本机路径、凭据、内部证据文件名或归档视频入口。
- 来源快照：`{manifest['git_commit']}`；数据边界：`{manifest['data_classification']}`。
"""


def _build_final_handoff(manifest: dict, modules: dict) -> dict:
    return {
        "schema_version": 1,
        "package": "SmartCS portfolio module handoff",
        "status": "ready",
        "target_task_id": "019f59c1-a1ab-7820-a310-ff2365afaee8",
        "project_id": "smartcs",
        "project_name": "SmartCS",
        "source_commit": manifest["git_commit"],
        "captured_at_utc": manifest["captured_at_utc"],
        "data_classification": manifest["data_classification"],
        "visible_disclosure": "公开虚构演示数据，不代表生产部署",
        "frontend_owner": "portfolio task",
        "module_order": [module["id"] for module in modules["modules"]],
        "files": {
            "facts": "materials/project-facts.json",
            "claims": "materials/claims.json",
            "copy": "materials/portfolio-copy.md",
            "modules": "materials/portfolio-modules.json",
            "integration_guide": "materials/portfolio-modules.md",
        },
        "evidence_catalog": {
            "demo_stdout": _source_ref(manifest, "demo.stdout.txt"),
            "rag_report": _source_ref(manifest, "rag-evaluation.json"),
            "pytest_stdout": _source_ref(manifest, "pytest.stdout.txt"),
        },
        "handoff_status_semantics": {
            "transitions": ["open", "assigned", "resolved"],
            "employee_observation": "resolved",
        },
        "asset_policy": {
            "archived_video_included": False,
            "dense_slide_images_as_page_content": False,
            "visual_reference_usage": "layout language only; bind page content to this handoff snapshot",
        },
        "integration_constraints": [
            "Preserve module order and evidence-backed meaning.",
            "Use responsive HTML text and existing portfolio components.",
            "Keep source, failure, and limitation text visible without hover.",
            "Do not expose local paths or raw evidence files in the public page.",
        ],
        "prohibited_claims": [
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
        ],
    }


def _build_copy(manifest: dict) -> str:
    retrieval = manifest["retrieval"]
    tests = manifest["tests"]
    recall = _percent(retrieval["recall_at_k"])
    failed = ", ".join(retrieval["failed_query_ids"])
    return f"""# SmartCS 作品集文案素材

> 这些文案受证据约束，供作品集任务调整排版；数字、状态顺序和限制保持不变。

## 一句话定位

面向企业内部员工的人事知识 Agent 后端工程样板，覆盖受治理的制度发布、带来源问答、受控转人工和多租户身份边界。

## 项目简介

SmartCS 面向企业内部员工，在 Python 后端中实现知识发布状态、授权来源引用、Agent 行动边界、跨租户拒绝和 RAG 回归验证。

## 简历 Bullet

- 设计并实现 Python 企业人事知识 Agent 后端，将 JWT 租户身份、制度审核状态、RAG 来源引用和 HR 转人工状态机组合为一条可验证业务链路。
- 建立固定语料 RAG 回归集，12 条查询 Recall@3 / MRR 均为 {recall}，保留失败问题 `{failed}`，并明确 HashEmbedding 非语义、vector 贡献为 0 的限制。
- 为认证、租户隔离、文档治理、检索和 Agent 工具调用建立自动化回归；本次同一 commit 验证结果为 {tests['passed']} passed、{tests['skipped']} skipped、0 failed。

## 面试讲法

1. **业务规则：** 制度在 `approved + current` 后进入员工检索；例外问题先生成待确认草稿。
2. **设计选择：** 用后端状态控制 `pending_review -> approved/current`，只允许当次授权检索来源进入回答，并把高影响工具调用限制为待确认草稿。
3. **权限边界：** JWT 中的租户和角色由 API 校验；跨租户 HR 数据请求直接返回 `403 tenant_access_denied`。
4. **工程验证：** 演示、检索评测和全量 pytest 在同一 Git commit 重新执行，输出经过脱敏并用 SHA-256 关联原始记录。
5. **评测边界：** 当前检索评测使用固定 curated corpus，HashEmbedding 不提供真实语义质量，指标仅作为离线回归门禁。

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

本目录提供事实、文案和证据索引，不包含作品集前端或 SmartCS 产品界面。

## 文件

- `project-facts.json`：机器可读的定位、能力、指标和限制。
- `claims.json`：每条可展示结论、业务价值、证据位置和适用边界。
- `portfolio-copy.md`：简历 Bullet、面试讲法、指标文案和禁止宣传内容。
- `portfolio-modules.json`：四个响应式作品集模块的文案、证据和移动端规则。
- `portfolio-modules.md`：供作品集任务使用的整合说明和验收边界。
- `../handoff.json`：最终模块顺序、文件索引、证据目录和禁止宣传合同。
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
    if output_dir.name != "materials":
        raise ValueError("output directory must be named materials")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_manifest(manifest, manifest_path.parent)

    outputs = {
        "readme": output_dir / "README.md",
        "facts": output_dir / "project-facts.json",
        "claims": output_dir / "claims.json",
        "copy": output_dir / "portfolio-copy.md",
        "modules": output_dir / "portfolio-modules.json",
        "guide": output_dir / "portfolio-modules.md",
        "handoff": output_dir.parent / "handoff.json",
    }
    modules = _build_modules(manifest)
    contents = {
        "readme": _build_readme(manifest),
        "facts": json.dumps(_build_facts(manifest), ensure_ascii=False, indent=2) + "\n",
        "claims": json.dumps(_build_claims(manifest), ensure_ascii=False, indent=2) + "\n",
        "copy": _build_copy(manifest),
        "modules": json.dumps(modules, ensure_ascii=False, indent=2) + "\n",
        "guide": _build_module_guide(manifest, modules),
        "handoff": json.dumps(
            _build_final_handoff(manifest, modules), ensure_ascii=False, indent=2
        )
        + "\n",
    }
    _validate_generated_texts(contents)

    output_dir.mkdir(parents=True, exist_ok=True)
    for label, path in outputs.items():
        path.write_text(contents[label], encoding="utf-8")
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
