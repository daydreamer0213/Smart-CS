# SmartCS -- 企业级多商户智能客服 SaaS

## 目标

生产级 SaaS，非面试 Demo。多商户、管理后台、数据分析面板。

## 环境

- conda 路径：D:\conda\Scripts\conda.exe
- 环境名：smart-cs，Python: `D:/conda-envs/smart-cs/python.exe`
- pip 缓存：`E:/smartcs-cache/pip/`（机械盘）
- HuggingFace 缓存：`E:/smartcs-cache/huggingface/`（机械盘，BGE 模型下载位置）
- LLM：DeepSeek API（OpenAI 兼容），base_url https://api.deepseek.com/v1
- embedding：也用 DeepSeek API（注意：DeepSeek 无专用 embedding 模型，用 chat 模型生成 embedding 或后续切换到专用 embedding 服务）

## 技术栈（已定）

FastAPI + SSE / ChromaDB（后续可升 Milvus）/ SQLAlchemy + Alembic / BM25 + RRF 融合
三层缓存 / 规则+LLM 意图分类 / 多租户 URL 隔离 / API Key 管理后台认证
structlog + request_id / 单页 HTML 前端

## 架构关键决策

| 决策 | 选择 | 说明 |
|------|------|------|
| 多租户隔离 | URL 路径 `/{tenant_slug}` + 独立 ChromaDB collection | collection 命名：`{tenant_slug}_knowledge` |
| API 版本 | `/api/v1/` 前缀 | 所有业务路由统一加前缀，`/health` 除外 |
| 数据库 | SQLite（开发）+ SQLAlchemy + Alembic | 生产切 PostgreSQL，Alembic 保证迁移一致 |
| 管理员认证 | API Key（Header: `X-Admin-Key`） | 先简单，后续补 JWT |
| Agent 编排 | 线性管道（暂不加 LangGraph） | 缓存→意图→检索→LLM，工具调用复杂后再引入框架 |
| 意图关键词 | 按租户配置，存在 `tenant.config_json` 里 | **不是全局写死**，不同行业关键词完全不同 |
| 错误响应格式 | `{"error": {"code": "...", "message": "..."}, "request_id": "..."}` | 所有异常统一此格式 |
| 请求追踪 | UUID4 → `X-Request-ID` 响应头 + structlog 绑定 | 全链路可追踪 |

## 详细方案

见 `C:\Users\39823\.claude\plans\inherited-giggling-puffin.md`（阶段 0-4 完整方案 + 数据模型 DDL + 管道流程图 + 管理后台 API 设计 + ShopMind 复用清单）。

## 参考项目

`D:\AAA\ShopMind-Agent\` 是之前的单店版本（LangGraph+Streamlit+BM25），可提取模式但不可复制文件结构：

| 来源 | SmartCS 目标位置 | 复用要点 |
|------|-----------------|---------|
| `src/config.py` | `app/config.py` | 30% — 加租户配置/数据库/ChromaDB/缓存/阈值 |
| `src/prompts.py` | `app/core/llm/prompts.py` | 70% — 改造为多租户，SYSTEM_PROMPT 按租户定制 |
| `src/graph/nodes.py`（意图） | `app/core/intent/classifier.py` | 80% — 规则+LLM 混合分类，关键词改为租户级 |
| `src/graph/nodes.py`（LLM） | `app/core/llm/client.py` | 80% — 加 fallback 链 |
| `src/utils/retrieval.py`（BM25） | `app/core/retrieval/bm25_index.py` | 60% — 按租户管理 BM25 实例 + 增量重建 |
| `src/tools/human.py` | 合入 `intent/classifier.py` | 90% — 直接可用 |
| `data/products.json` | `data/seed/faq_template.json` | 结构参考 |
| `data/policies.json` | `data/seed/faq_template.json` | 结构参考 |
| `tests/eval_cases.json` | `tests/` | 80% — 加多租户 FAQ 用例 |

## 项目结构（全量，阶段 0 一次性创建）

```
smart-cs/
├── .env.example                  # 配置模板
├── .gitignore                    # .env / __pycache__ / *.db / chroma_data/ / .pytest_cache/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── tenant.py
│   │   ├── knowledge.py
│   │   ├── conversation.py
│   │   └── analytics.py          # 占位 — 后续存物化视图/聚合查询结果
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── chat.py
│   │   ├── knowledge.py
│   │   ├── analytics.py
│   │   └── tenant.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py
│   │   ├── health.py
│   │   ├── chat.py
│   │   └── admin/
│   │       ├── __init__.py
│   │       ├── auth.py
│   │       ├── knowledge.py
│   │       └── analytics.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── retrieval/
│   │   │   ├── __init__.py
│   │   │   ├── vector_store.py
│   │   │   ├── bm25_index.py
│   │   │   └── fusion.py
│   │   ├── intent/
│   │   │   ├── __init__.py
│   │   │   └── classifier.py
│   │   ├── cache/
│   │   │   ├── __init__.py
│   │   │   ├── exact.py
│   │   │   └── semantic.py
│   │   ├── conversation/
│   │   │   ├── __init__.py
│   │   │   └── memory.py
│   │   └── llm/
│   │       ├── __init__.py
│   │       ├── client.py
│   │       └── prompts.py        # 提示词模板（从 ShopMind 提取，改造为多租户）
│   ├── services/
│   │   ├── __init__.py
│   │   ├── chat_service.py
│   │   ├── knowledge_service.py
│   │   └── analytics_service.py
│   └── middleware/
│       ├── __init__.py
│       ├── tenant.py             # 阶段 0 就实现（不是占位）
│       ├── logging.py
│       ├── ratelimit.py
│       └── error_handler.py
├── admin-static/
│   ├── index.html
│   ├── css/                      # 阶段 3 填充
│   └── js/                       # 阶段 3 填充
├── static/
│   └── chat.html
├── migrations/                   # alembic init 生成
├── data/seed/
│   ├── faq_template.json         # FAQ 种子数据模板
│   └── tenant_sample.json        # 示例商户配置
├── tests/
│   ├── __init__.py
│   ├── conftest.py               # 阶段 0 就绪
│   ├── test_chat_api.py          # 占位（后续阶段实现）
│   ├── test_admin_knowledge_api.py
│   ├── test_admin_analytics_api.py
│   ├── test_retrieval.py
│   ├── test_cache.py
│   ├── test_intent.py
│   ├── test_memory.py
│   ├── test_tenant_isolation.py
│   └── test_e2e.py
├── alembic.ini
├── requirements.txt
└── README.md
```

---

## 阶段 0 — 项目骨架（今晚，不做功能）

建一个"什么都没有但结构正确"的项目骨架。所有业务路由返回 `{"status":"not_implemented"}`，models 只定义表不写逻辑。

### Step 1：环境

```bash
conda create -n smart-cs python=3.12
pip install fastapi uvicorn[standard] chromadb sqlalchemy alembic pydantic pydantic-settings python-dotenv structlog jieba rank-bm25 openai httpx pytest pytest-asyncio
```

### Step 2：建目录 + 空文件

按上方的项目结构全量创建。每个 `__init__.py` 留空，每个 `.py` 写 docstring + 占位。`.env.example` 和 `.gitignore` 阶段 0 就建好。

### Step 3：写骨架代码

#### 3.1 config.py — 完整实现

pydantic-settings `BaseSettings`，从 `.env` 读取，字段：

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `database_url` | `sqlite:///./smartcs.db` | 开发用 SQLite |
| `chroma_persist_dir` | `./chroma_data` | ChromaDB 持久化目录 |
| `llm_api_key` | — | DeepSeek API Key |
| `llm_base_url` | `https://api.deepseek.com/v1` | OpenAI 兼容端点 |
| `llm_model` | `deepseek-chat` | 对话模型 |
| `embedding_model` | `deepseek-chat` | embedding 模型（暂无专用模型，后续可换） |
| `l1_cache_ttl` | `300` | L1 精确缓存过期秒数 |
| `l2_cache_threshold` | `0.85` | L2 语义缓存余弦相似度阈值 |
| `intent_confidence_threshold` | `0.6` | 意图分类置信度阈值 |
| `max_context_tokens` | `2000` | 上下文窗口最大 token 数 |
| `max_conversation_turns` | `10` | 滑动窗口最大轮数 |
| `rate_limit_per_minute` | `30` | 每租户每分钟请求上限 |
| `log_level` | `INFO` | structlog 日志级别 |

同时生成 `.env.example`，内容为所有字段 + 默认值 + 注释。

#### 3.2 models/ — 只定义表结构，不写逻辑

**base.py**：`declarative_base()` + `TimestampMixin`（`id: UUID` 主键, `created_at`, `updated_at`）。

**tenant.py**：
- `Tenant`（slug unique, name, config_json JSON, is_active bool）
- `AdminApiKey`（tenant_id FK, key_hash, label, last_used_at）

**knowledge.py**：
- `KnowledgeItem`（tenant_id FK, category_id FK, question, answer, keywords, embedding_id — ChromaDB 文档 ID, status: active/draft/archived）
- `Category`（tenant_id FK, name, description, sort_order）

**conversation.py**：
- `Conversation`（tenant_id FK, session_id, visitor_id, status: active/closed/handed_off, message_count）
- `Message`（conversation_id FK, role: user/assistant/system, content, intent, cache_hit: L1/L2/miss, sources_json, latency_ms）

**analytics.py**：占位，docstring 注明后续存物化视图/聚合数据。

#### 3.3 middleware/ — 完整实现（不是占位）

**logging.py**：structlog 配置 + `request_id` contextvar（UUID4 生成）+ 注入 `X-Request-ID` 响应头 + 请求/响应日志。

**error_handler.py**：全局异常捕获，`HTTPException` 透传，未处理异常返回统一格式：
```json
{"error": {"code": "INTERNAL_ERROR", "message": "..."}, "request_id": "..."}
```

**tenant.py**：从 URL path 提取 `tenant_slug` → 查 `tenants` 表 → 注入 `request.state.tenant`。租户不存在返回 404 JSON。**阶段 0 就实现，所有 `/api/v1/{tenant_slug}/` 路由依赖它。**

#### 3.4 api/ — 路由骨架

**deps.py**：`get_db()`（yield session），`get_tenant(db, tenant_slug)`（查库，不存在则 404），`verify_admin(db, tenant, request)`（从 `X-Admin-Key` header 验证）。

**health.py**：`GET /health` → `{"status":"ok","version":"0.1.0"}`。不需要租户上下文。

**其余所有路由**：返回 `{"status":"not_implemented"}`，docstring 说明后续用途。

API 路径约定：
- `/health` — 健康检查（无前缀，无租户）
- `/api/v1/{tenant_slug}/chat` — 客服对话
- `/api/v1/admin/{tenant_slug}/knowledge` — 管理后台知识库 CRUD
- `/api/v1/admin/{tenant_slug}/analytics` — 管理后台数据分析

#### 3.5 core/ — 全部占位

每个模块只写 docstring + 函数签名（`pass` / `raise NotImplementedError`）。

#### 3.6 schemas/ — 全部占位

每个模块定义空的 Pydantic model 占位 + docstring。

#### 3.7 services/ — 全部占位

每个模块写函数签名 + docstring。

#### 3.8 tests/

**conftest.py**：完整实现 — test app fixture（内存 SQLite `sqlite:///:memory:`），client fixture（`httpx.AsyncClient`），db fixture（独立事务自动回滚）。

**其余测试文件**：占位 + docstring 说明测试范围。

### Step 4：验证

```bash
uvicorn app.main:app --reload
curl http://localhost:8000/health
# → {"status":"ok","version":"0.1.0"}

curl http://localhost:8000/api/v1/demo/chat
# → {"status":"not_implemented"}

pytest tests/ -v
# 确认无导入错误，conftest fixtures 正常工作
```

---

## 核心原则

- 阶段 0 只写骨架，不写业务逻辑
- 每个空模块必须有 docstring 说明后续用途
- **middleware（tenant / logging / error_handler）和 config 是少数要真正写完运行的模块**
- 所有文件创建后跑 `pytest tests/ -v` 确认没导入错误
- 参考 ShopMind-Agent 时只提取逻辑模式，不复制文件结构
- **意图关键词按租户配置，不写全局常量**

## tenant.config_json 结构（约定 schema）

虽为 JSON 自由字段，但后续各模块依赖它取租户级配置，阶段 0 需约定最小结构：

```json
{
  "human_keywords": ["人工", "客服", "经理", "投诉"],
  "system_prompt_append": "",
  "model_override": null,
  "cache_ttl_override": null,
  "intent_threshold_override": null,
  "handoff_enabled": true
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `human_keywords` | `list[str]` | 触发转人工的关键词，按行业差异巨大 |
| `system_prompt_append` | `str` | 追加到通用 system prompt 后的商户专属说明 |
| `model_override` | `str \| null` | 覆盖全局 `llm_model`，null 则用全局默认 |
| `cache_ttl_override` | `int \| null` | 覆盖全局 `l1_cache_ttl`，null 则用全局默认 |
| `intent_threshold_override` | `float \| null` | 覆盖全局意图置信度阈值，null 则用全局默认 |
| `handoff_enabled` | `bool` | 该租户是否启用转人工功能 |

阶段 0 只定义 schema 文档，不做校验逻辑。后续 `intent/classifier.py`、`cache/exact.py`、`llm/client.py` 等模块从此对象取租户级配置。

## 关键注意事项

- **SQL ↔ ChromaDB 双写一致性**：knowledge_service 后续需处理（先写 SQL，再写 ChromaDB，失败回滚策略）
- **BM25 索引**：启动时按租户构建，知识变更时重建（数据量大后考虑增量更新）
- **缓存失效**：知识条目增删改时必须同步失效对应租户的 L1 + L2 缓存
- **embedding 模型**：DeepSeek 目前无专用 embedding 模型，阶段 0 用 chat 模型顶替，后续评估切换（如 text-embedding-3-small 等）
- **租户创建**：阶段 0-2 手动插数据库或脚本，自助注册不在本次范围

## 后续阶段

阶段 1-4 见详细方案 `inherited-giggling-puffin.md`：
- 阶段 1：知识库引擎（CRUD + 向量化 + RRF 检索）
- 阶段 2：智能对话（意图分类 + LLM 管道 + 缓存 + 多轮对话）
- 阶段 3：流式 + 前端（SSE + 客服挂件 + 管理后台）
- 阶段 4：数据分析 + 生产加固（分析面板 + 限流 + Docker）
