# SmartCS — 企业级多商户智能客服 SaaS

## 环境

- conda: `D:/conda/Scripts/conda.exe`，环境 `smart-cs`，Python: `D:/conda-envs/smart-cs/python.exe`
- pip 缓存: `E:/smartcs-cache/pip/`，HuggingFace: `E:/smartcs-cache/huggingface/`
- LLM: DeepSeek API (`deepseek-chat`)，Embedding: 阿里云 DashScope (`text-embedding-v3`)
- 密钥在 `.env`

## 当前状态

- 4 阶段全部交付 + Agent 升级（LangGraph ReAct）+ 文档导入（Phase 1.1）
- **94 项测试全过**，pre-push review PASS
- Roadmap: `docs/planning/ROADMAP.md`（M1: 生产就绪, M2: 运维增强）
- 下一个任务: **Phase 1.2 JWT 认证** 或 **Phase 1.3 租户自助注册**

## 强制开发流程

**所有非平凡修改必须走标准流程，禁止跳过 skill 直接写代码：**

### 新功能 / 设计改动
```
brainstorming → writing-plans → subagent-driven-development → pre-push-review → finishing-a-development-branch
```
1. `brainstorming` — 出设计 spec（`docs/superpowers/specs/`）
2. `writing-plans` — 出实现计划（`docs/superpowers/plans/`）
3. `subagent-driven-development` — 逐任务派发实现+审查
4. `pre-push-review` — 推送前 4 维审查
5. `finishing-a-development-branch` — 收尾

### 修 Bug
```
systematic-debugging → 找到根因 → 修 → 补测试 → 验证
```
**禁止猜测修复。** 必须先重现、定位根因，再动手。

### 项目追踪
- 继续开发：`project-orchestration` → `resume-work` → `start-next-phase`
- 阶段性审查：`pre-push-review` + `simplify`

## 技术栈与关键决策

| 项 | 选型 |
|----|------|
| Agent 架构 | LangGraph ReAct（agent + tools 循环），2 个工具: search_knowledge / handoff_to_human |
| 嵌入 | 阿里云 DashScope text-embedding-v3 |
| 向量库 | ChromaDB，collection: `{tenant_slug}_knowledge` |
| 检索 | BM25 + 向量 RRF 融合 |
| 缓存 | L1 精确 + L2 语义（闲聊快路 0 API 调用） |
| 流式 | SSE via LangGraph astream_events |
| 认证 | API Key（Header: `X-Admin-Key`）→ 下一步改 JWT |
| 数据库 | SQLite（开发），SQLAlchemy + Base.metadata.create_all() |

## 编码约定

- 中文交流，代码注释尽量少（只写 WHY 不写 WHAT）
- model ID 全部 `String(36)` UUID，继承 `Base, TimestampMixin`
- API 路径: `/health`（无前缀），`/api/v1/{slug}/chat`，`/api/v1/admin/{slug}/...`
- 错误格式: `{"error": {"code": "...", "message": "..."}, "request_id": "..."}`
- 测试优先，改完立刻跑 `pytest tests/ -v`

## 项目结构（仅列出主要目录）

```
smart-cs/
├── app/
│   ├── main.py, config.py, db.py
│   ├── models/         — Tenant, KnowledgeItem, Document, DocumentChunk, Conversation, Message …
│   ├── schemas/        — chat, knowledge, document, analytics, tenant
│   ├── api/            — deps, health, chat, admin/{auth,knowledge,document,analytics}
│   ├── core/
│   │   ├── agent/      — graph.py, state.py, tools.py
│   │   ├── embedding/  — OpenAI/BGE provider
│   │   ├── retrieval/  — vector_store, bm25_index, fusion
│   │   ├── cache/      — exact (L1), semantic (L2)
│   │   ├── llm/        — client, prompts
│   │   └── parsing/    — parser.py, chunker.py (文档导入)
│   ├── services/       — chat_service, knowledge_service, document_service, analytics_service
│   └── middleware/      — logging, error_handler, tenant, ratelimit
├── admin-static/       — 管理后台 SPA (知识库 + 分析 + 文档管理)
├── static/chat.html    — 客服挂件
├── tests/              — 94 tests, conftest 用内存 SQLite + fake embedding
└── docs/
    ├── planning/       — ROADMAP.md, MILESTONE.md
    └── superpowers/    — specs/, plans/
```
