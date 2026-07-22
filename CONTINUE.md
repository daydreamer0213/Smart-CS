# SmartCS 项目接手说明

复制给新会话使用。

---

你正在维护已冻结的 SmartCS `v0.1.0` 求职作品集快照。请使用中文，直接务实。除非用户明确解除冻结，否则不要继续扩功能；只复现和修复缺陷、处理敏感信息或维护求职展示材料。

## 项目定位

SmartCS 不是普通 FAQ 聊天机器人，也不再只包装成“智能客服后台”。当前定位是：

> 多租户企业 HR 服务 Agent 后端样板：员工登录后查询本人有权查看的制度，获得可读来源；制度未覆盖的例外经员工确认后进入 HR 支持生命周期。

它服务郭铭福求职，重点证明：

- Python AI 后端工程能力。
- RAG / 文档导入 / 知识治理。
- 受限 Agent 工具调用：制度检索、澄清、转人工草稿和本人请求状态。
- JWT / API Key 多租户身份边界。
- 受控 HR 支持写操作：Agent 只生成草稿，员工显式确认后才建单。
- 可读来源、审计日志、幂等确认、错误处理和测试覆盖。

不要把 SmartCS 讲成两年前的“FAQ 客服机器人”。要讲成企业 AI 应用落地时必须处理的后端工程闭环。

## 当前真实路径

项目根目录：

```text
D:\2026.07.09\AAA\smart-cs
```

旧文档里的 `D:\AAA`、`D:\conda-envs`、`D:\conda` 都是历史路径，不要使用。

## 环境

```text
Python: D:\2026.07.09\conda-envs\smart-cs\python.exe
conda:  D:\2026.07.09\conda\Scripts\conda.exe
```

当前 Python 版本为 `3.12.13`。Docling/Tesseract 是可选高级解析依赖，不在基础 `requirements.txt` 中；需要时按 `docs/operations/docling-ocr-setup.md` 安装。

大文件和依赖缓存放 D 盘：

```text
D:\DevData\smartcs\pip
D:\DevData\smartcs\huggingface
D:\DevData\smartcs\torch
```

## 当前状态

已完成：

- 2026-07-22 当前 `main` 完整回归为 `405 passed, 4 skipped`；`v0.1.0` 标签快照仍保留原始 `403 passed, 4 skipped` 记录。
- 新电脑环境恢复，依赖和缓存路径整理到 D 盘。
- JWT 登录、多租户身份边界、owner/admin/agent/employee 角色。
- 企业知识库 RAG：FAQ 与文档分块统一检索，文档导入、分块、ChromaDB、BM25、后台治理。
- M2 文档智能与知识治理已交付：M2-2 parser gate 历史成功报告为 9 fixtures、8 parsed、1 encrypted blocked、18/18 parsed facts、18/18 chunk facts 和 provenance 通过；CPU Docling/OCR 在当前内存压力下可波动。
- M2-3/M2-4 已交付质量门禁、内容寻址原件留存、审批发布、版本/有效期、当前索引代次和失败安全 reindex。
- M2-5 retrieval gate 已交付：8 indexed fixtures、11 curated facts-only chunks、12 golden queries、`top_k=3`；Recall@3 `11/12 = 91.67%`、MRR `91.67%`、已召回来源 provenance `100%`、gate passed，失败项为 `payroll-contact`。
- M2-5 贡献统计为 BM25 11、vector 0；HashEmbedding 非语义，只验证向量通路，不能表述为混合语义检索质量。评测不调用 FastGPT、LLM 或 LLM judge，且不等于通用 PDF/OCR 准确率或生产 SLA。
- 统一员工 Agent 入口：`/api/v1/{tenant_slug}/assistant/*`。
- HR Skills：制度检索、澄清、待确认转人工草稿、本人请求状态。
- 后端保留 `[source:<id>]` 机器引用做授权校验；API 的 `display_reply` 和员工页面显示中文制度标题，不暴露裸 UUID。
- `/static/assistant.html` 员工页面使用真实 HR 转人工契约：读取 `pending_handoff`，并通过 `/api/v1/{tenant_slug}/hr-support/drafts/{draft_id}/confirm` 完成员工确认。
- 未认证旧 `/chat` 路由已下线；`/api/v1/{tenant_slug}/assistant/*` 是 HR 主 API，`/business` 仅保留为 JWT 保护的 Sales Copilot Lab 历史回归面。
- 阶段 2C 已完成：修复主入口限流覆盖、BM25 增量语料丢失和文档分块无法被 Agent 检索的问题，并补齐对应回归测试。
- 离线 `hash` embedding provider，用于无外部额度时稳定演示。
- README、求职交付包、最终面试表达稿和 3 分钟演示稿。

## 核心文件

- `README.md`
- `docs/README.md`
- `docs/interview/SMARTCS_DELIVERY_PACKAGE.md`
- `docs/interview/SMARTCS_FINAL_PITCH.md`
- `docs/interview/SMARTCS_INTERVIEW.md`
- `docs/interview/SMARTCS_DEMO_SCRIPT.md`
- `docs/operations/rag-evaluation-m2-5.md`
- `scripts/evaluate_rag_retrieval.py`
- `scripts/demo_enterprise_flow.py`
- `app/api/auth.py`
- `app/api/assistant.py`
- `app/api/hr_support.py`
- `app/core/agent/hr_agent.py`
- `app/core/agent/tools.py`
- `app/services/assistant_service.py`
- `app/services/hr_support_service.py`
- `app/models/user.py`
- `app/models/hr.py`
- `app/core/embedding/hash_provider.py`
- `tests/test_auth.py`
- `tests/test_assistant_api.py`
- `tests/test_assistant_agent.py`
- `tests/test_business_api.py`

## 常用命令

以下命令都从当前仓库根目录执行：

```powershell
D:\2026.07.09\conda-envs\smart-cs\python.exe -m pytest tests/ -v

D:\2026.07.09\conda-envs\smart-cs\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

D:\2026.07.09\conda-envs\smart-cs\python.exe scripts\demo_enterprise_flow.py

D:\2026.07.09\conda-envs\smart-cs\python.exe scripts\evaluate_rag_retrieval.py --fixture-dir tests\fixtures\documents --work-dir D:\DevData\smartcs\rag-eval\m2-5 --output D:\DevData\smartcs\benchmarks\m2-5-rag-evaluation.json --environment-label local-windows-cpu
```

离线演示建议使用临时数据库和临时 Chroma 目录：

```powershell
$demoRoot="D:/DevData/smartcs/demo-" + (Get-Date -Format "yyyyMMdd-HHmmss")
New-Item -ItemType Directory -Force -Path $demoRoot | Out-Null
$env:EMBEDDING_PROVIDER="hash"
$env:DATABASE_URL="sqlite:///$demoRoot/smartcs-demo.db"
$env:CHROMA_PERSIST_DIR="$demoRoot/chroma"
$env:LOG_DIR="$demoRoot/logs"
```

## 求职讲法

一句话：

> SmartCS 是一个多租户企业员工 Agent 后端，员工登录后按角色获得企业知识；制度文档经过解析、质量门禁、审批发布与来源溯源后才可检索，例外操作必须显式确认、重新校验并留下审计。

不要夸大：

- 不是已经商业上线的 SaaS。
- 离线 HashEmbedding 只是演示和向量通路方案，不代表生产语义向量质量；M2-5 当前 11/12 命中均由 BM25 贡献。
- `/business/*` 是虚构数据驱动的 Sales Copilot Lab，不是 SmartCS 的 HR 主路径或通用 CRM 集成平台。
- UI 不是主卖点，主卖点是 Python AI 后端、RAG、Agent、权限边界、受控写操作和测试。

## 冻结与解冻规则

`v0.1.0` 已完成发布前检查并进入维护冻结。未收到用户明确的“解除冻结”指令时，不启动 M3/M4，不回退为 CRM 扩功能，也不重新包装 FAQ。

1. 当前允许：复现并修复缺陷、依赖或密钥安全处理、求职材料和演示证据维护。
2. 解冻后如确有可调用平台，M3 只接一个真实 HR/OA 沙箱；不自研 HRIS。
3. 只有真实试点需要时才进入 M4 的异步导入、可观测、通知/SLA、SSO/OIDC、CI/CD 与生产密钥治理。
4. 投递演示先运行 `docs/operations/rag-evaluation-m2-5.md` 的命令，再按 `docs/interview/SMARTCS_DEMO_SCRIPT.md` 展示带来源的制度问答。
