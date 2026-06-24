# SmartCS 继续开发提示词

复制以下内容到新会话——

---

我正在开发 SmartCS，一个企业级多商户智能客服 SaaS 系统。项目在 `D:\AAA\smart-cs\`。

## 环境

- Python: `D:/conda-envs/smart-cs/python.exe`
- conda: `D:/conda/Scripts/conda.exe`
- pip 缓存: `E:/smartcs-cache/pip/`
- HuggingFace: `E:/smartcs-cache/huggingface/`
- LLM: DeepSeek API (`deepseek-chat`), key 在 `.env`
- Embedding: 阿里云 DashScope (`text-embedding-v3`), key 在 `.env`
- 项目说明书: `CLAUDE.md`

## 已完成

4 个阶段全部交付，50 个 commit，43 项测试全过：

- **阶段 0**: 项目骨架 — config, models (6 表), middleware (logging/error_handler/tenant/ratelimit), Alembic, test fixtures
- **阶段 1**: 知识引擎 — 管理后台 CRUD (8 端点), ChromaDB VectorStore, BM25, RRF fusion, embedding 抽象层 (OpenAI/BGE/阿里云), SQL↔ChromaDB 双写
- **阶段 2**: 智能对话 — 意图分类 (规则+LLM), LLM 客户端 (3 次重试), L1/L2 缓存, 滑动窗口 (tiktoken), 对话持久化, SSE 流式
- **阶段 3**: 前端 — 客服聊天挂件 (701 行), 管理后台 SPA (997 行, 知识库 CRUD + 分析面板)
- **阶段 4**: 生产加固 — 分析服务+API, 令牌桶限流, Prometheus /metrics, JSONL 日志持久化, Docker, 健康检查 (DB+ChromaDB)

## 端到端已跑通

```bash
启动: D:/conda-envs/smart-cs/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
验证: curl -X POST http://127.0.0.1:8000/api/v1/demo/chat -H "Content-Type: application/json" -d '{"session_id":"","message":"退货需要几天"}'
测试: D:/conda-envs/smart-cs/python.exe -m pytest tests/ -v
前端: http://127.0.0.1:8000/static/chat.html (客服)
       http://127.0.0.1:8000/admin/ (管理后台)
```

## 已知待修复

1. `test_admin_route_extracts_correct_slug` 里的 admin 路由正则已经修好了，但 admin 端点因为需要 API Key 认证，没 key 时返回 401，不是 200。
2. `test_llm_client.py::TestOutput` 被 pytest 当成测试类收集，加 `__test__ = False` 即可消除 warning。

## 可做的后续工作

按优先级排列：

**P0 — 验收（必须先做）:**
1. 浏览器打开 `http://127.0.0.1:8000/static/chat.html`，发几条消息看看流式回复效果
2. 打开 `http://127.0.0.1:8000/admin/`，填入 API Key，CRUD 知识条目
3. `docker-compose up` 验证容器化部署

**P1 — 功能补全:**
4. 文档导入 — 支持上传 PDF/Word，解析→分块→嵌入→入库
5. JWT 认证 — 替换 API Key，加用户注册/登录
6. 租户自助注册 — 注册页面 + 自动创建 ChromaDB collection

**P2 — 运维增强:**
7. CI/CD — GitHub Actions 自动化测试 + Docker 构建
8. WebSocket 实时对话 — 双向通信
9. Milvus 升级 — ChromaDB → Milvus 迁移

## 关键设计约束

- 意图关键词按租户配置（`tenant.config_json.human_keywords`），不写全局常量
- 知识删除是软删除（status → archived）
- ChromaDB collection 命名: `{tenant_slug}_knowledge`
- API 路径: `/health` (无前缀), `/api/v1/{slug}/chat`, `/api/v1/admin/{slug}/...`
- 错误格式: `{"error": {"code": "...", "message": "..."}, "request_id": "..."}`
- 所有 model ID 是 String(36) UUID
- 中间件顺序: Logging → RateLimit → Tenant → Route

## 目录速览

```
smart-cs/
├── app/
│   ├── main.py, config.py, db.py
│   ├── models/        — Tenant, AdminApiKey, KnowledgeItem, Category, Conversation, Message
│   ├── schemas/       — chat, knowledge, analytics, tenant
│   ├── api/           — deps, health, chat, admin/auth, admin/knowledge, admin/analytics
│   ├── core/
│   │   ├── embedding/ — OpenAI/BGE provider + factory
│   │   ├── retrieval/ — vector_store, bm25_index, fusion
│   │   ├── intent/    — classifier (rule+LLM)
│   │   ├── cache/     — exact (L1), semantic (L2)
│   │   ├── conversation/ — memory (sliding window)
│   │   └── llm/       — client (retry+stream), prompts
│   ├── services/      — chat_service, knowledge_service, analytics_service
│   └── middleware/     — logging, error_handler, tenant, ratelimit
├── static/chat.html
├── admin-static/index.html
├── tests/ (43 tests)
├── data/seed/ — tenant_sample.json, faq_template.json (10 条中文 FAQ)
├── Dockerfile, docker-compose.yml
└── docs/superpowers/ — 设计文档和计划
```
