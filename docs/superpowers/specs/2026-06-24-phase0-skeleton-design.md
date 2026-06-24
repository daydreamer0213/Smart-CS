# SmartCS 阶段 0 — 项目骨架设计

## 目标

建一个"什么都没有但结构正确"的项目骨架。所有业务路由返回 `{"status":"not_implemented"}`，models 只定义表不写逻辑。唯一完整实现的是 config、middleware（tenant/logging/error_handler）、tests/conftest。

## 验收标准

1. `pytest tests/ -v` 全部通过
2. `/health` 返回 200
3. `/api/v1/demo/chat` 返回 `{"status":"not_implemented"}`
4. `alembic upgrade head` 建表成功
5. demo 租户种子数据自动初始化（lifespan）
6. request_id 全链路可追踪（请求头→structlog→响应头）

## 架构决策

| 决策 | 选择 |
|------|------|
| API 路径 | `/health`（无前缀），业务路由 `/api/v1/{tenant_slug}/...` |
| 多租户 | URL path slug → 查 DB → `request.state.tenant` |
| ChromaDB 隔离 | collection 命名 `{tenant_slug}_knowledge`（阶段 1 实现） |
| 数据库 | SQLite（开发），Alembic autogenerate 迁移 |
| 错误格式 | `{"error": {"code": "...", "message": "..."}, "request_id": "..."}` |
| 意图关键词 | 租户级配置，存 `tenant.config_json`，不写全局常量 |

## 执行策略：5 层堆叠

```
Layer 1: config + models + schemas + .env.example + .gitignore
Layer 2: middleware (logging / error_handler / tenant)
Layer 3: api (deps / health / chat / admin)
Layer 4: main.py + alembic + seed data
Layer 5: tests + core/ + services/ + static/
```

每层写完立即验证，出错范围控制在 3-5 个文件内。

## Layer 1 — 数据层

### config.py (12 字段)

| 字段 | 默认值 |
|------|--------|
| `database_url` | `sqlite:///./smartcs.db` |
| `chroma_persist_dir` | `./chroma_data` |
| `llm_api_key` | (必填) |
| `llm_base_url` | `https://api.deepseek.com/v1` |
| `llm_model` | `deepseek-chat` |
| `embedding_model` | `deepseek-chat` |
| `l1_cache_ttl` | `300` |
| `l2_cache_threshold` | `0.85` |
| `intent_confidence_threshold` | `0.6` |
| `max_context_tokens` | `2000` |
| `max_conversation_turns` | `10` |
| `rate_limit_per_minute` | `30` |
| `log_level` | `INFO` |

### models/

- **base.py**: `Base` + `TimestampMixin` (id UUID PK, created_at, updated_at)
- **tenant.py**: `Tenant` (slug unique, name, config_json JSON, is_active), `AdminApiKey` (FK tenant, key_hash, label)
- **knowledge.py**: `KnowledgeItem` (FK tenant/category, question, answer, embedding_id, status), `Category` (FK tenant, name)
- **conversation.py**: `Conversation` (FK tenant, session_id, visitor_id, status), `Message` (FK conversation, role, content, intent, cache_hit, sources_json, latency_ms)
- **analytics.py**: 占位

所有 model 在 `models/__init__.py` 中导入，确保 `Base.metadata.create_all` 能发现。

### schemas/

全部占位，每个文件一个空 Pydantic model + docstring。

### tenant.config_json schema

```json
{
  "human_keywords": ["人工", "客服"],
  "system_prompt_append": "",
  "model_override": null,
  "cache_ttl_override": null,
  "intent_threshold_override": null,
  "handoff_enabled": true
}
```

## Layer 2 — 中间件层

### logging.py
- `contextvars.ContextVar[str]` 存 request_id
- UUID4 生成，注入 `X-Request-ID` 响应头
- structlog 配置：JSON 格式 + 时间戳 + request_id 绑定

### error_handler.py
- `HTTPException` 透传，转换为 JSON error 格式
- 未处理异常 → `{"error": {"code": "INTERNAL_ERROR", "message": "..."}, "request_id": "..."}`

### tenant.py
- `@app.middleware("http")` 
- 从 `request.url.path` 正则提取 slug
- 查库 → `request.state.tenant` 或 `JSONResponse(404)`

## Layer 3 — 路由层

### deps.py
- `get_db()`: yield SQLAlchemy session
- `get_tenant()`: 查库，不存在则 HTTPException(404)
- `verify_admin()`: 从 X-Admin-Key header 验证

### 路由约定
- `/health` — 健康检查
- `/api/v1/{tenant_slug}/chat` — 客服对话（占位）
- `/api/v1/admin/{tenant_slug}/knowledge` — 知识库管理（占位）
- `/api/v1/admin/{tenant_slug}/analytics` — 数据分析（占位）

## Layer 4 — 组装层

### main.py
- `create_app()` 工厂函数
- lifespan: `Base.metadata.create_all` + demo tenant 种子
- 注册中间件（tenant → logging → error_handler）
- 注册路由（health + chat + admin）
- mount 静态文件（/static, /admin）

### alembic
- `alembic init migrations` → 改 alembic.ini → autogenerate initial migration

### 种子数据
- lifespan 中检查 tenants 表是否为空
- 空则插入 demo 租户: `{slug: "demo", name: "DemoStore", config_json: {...}}`

## Layer 5 — 测试+占位

### conftest.py (完整实现)
- app fixture: `create_app()` + 内存 SQLite
- client fixture: `httpx.AsyncClient(app, base_url="http://test")`
- db fixture: 独立事务 + rollback

### core/ + services/ (全部占位)
每个文件: docstring + `raise NotImplementedError` 函数签名

### 测试文件 (9 个占位)
docstring 说明测试范围，阶段 1-4 填充
