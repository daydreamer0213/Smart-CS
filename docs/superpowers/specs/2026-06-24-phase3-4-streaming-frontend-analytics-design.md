# SmartCS 阶段 3+4 — 流式前端 + 分析面板 + 生产加固

## 阶段 3 — SSE 流式 + 前端

### SSE 流式端点
- `GET /api/v1/{tenant_slug}/chat/stream?session_id=...&message=...` → `text/event-stream`
- SSE 事件类型：`delta`（增量 token），`sources`（检索源），`done`（完成 JSON）
- 实现：`chat_service.process_chat_stream()` — 异步生成器，yield SSE 事件
- LLM 客户端新增 `chat_stream()` 方法，`stream=True`

### 客服聊天挂件 (`static/chat.html`)
- 单页，零构建，vanilla HTML/CSS/JS
- 功能：消息输入框 → SSE 流式响应 → 逐字显示 → 显示引用来源
- 响应式，可嵌入 iframe
- 自动生成 session_id（localStorage）

### 管理后台 (`admin-static/`)
- 单页应用，tab 切换：知识库管理 / 数据分析
- 知识库：列表(分页+搜索) / 新增表单 / 编辑模态框 / 删除确认 / 批量导入
- 数据分析：概览仪表板 / 意图饼图 / 日趋势折线 / 知识命中排行
- API Key 认证（存储到 localStorage）

## 阶段 4 — 数据分析 + 生产加固

### 分析服务
- `analytics_service.get_overview(tenant_id, days)` → 对话总数、平均延迟、命中率、转人工率
- `analytics_service.get_intent_distribution(tenant_id, days)` → faq/human 分布
- `analytics_service.get_daily_trend(tenant_id, days)` → 每日对话量、命中率
- `analytics_service.get_top_knowledge(tenant_id, days, limit)` → 被引用最多的知识条目

### 速率限制
- 简易 token bucket，每租户每分钟 30 请求（通过 `settings.rate_limit_per_minute`）
- `X-RateLimit-Remaining` 响应头

### Docker
- `Dockerfile`：Python 3.12-slim + pip install + uvicorn
- `docker-compose.yml`：app + ChromaDB volume

### 测试补全
- test_e2e.py 端到端完整对话链路
- test_tenant_isolation.py 已存在，补全验证场景
