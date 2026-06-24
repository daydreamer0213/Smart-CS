# SmartCS 阶段 2 — 智能对话设计

## 目标

实现客服对话完整管道：意图分类 → 混合检索 → LLM 生成 → 缓存 → 持久化。两晚交付。

## 管道流程

```
POST /api/v1/{tenant_slug}/chat { session_id, message }
  → L1 精确缓存（hit → 直接返回）
  → L2 语义缓存（hit → 直接返回）
  → 意图分类（规则: human_keywords / retrieval_hit → LLM 兜底）
  → human → 转人工话术
  → faq → 混合检索（ChromaDB + BM25 + RRF）
  → 滑动窗口上下文
  → LLM 生成
  → 更新 L1 + L2 缓存
  → 持久化 → ChatResponse
```

## 关键决策

| 决策 | 选择 |
|------|------|
| 意图分类 | 规则 + LLM 双阶段，置信度 < 0.6 → human |
| 意图标签 | 仅 faq / human（不需要 shop/product/policy/order 五分类） |
| LLM 备份 | 无备用 API，加重试（3 次，exponential backoff 1s/2s/4s） |
| 缓存 | L1 精确（TTL 300s）+ L2 语义（cosine >= 0.85） |
| 转人工 | 匹配 human_keywords 或 LLM 低置信度 → 固定话术 |
| 上下文 | tiktoken 计数，max_tokens=2000，max_turns=10 |

## Night 3 — 意图 + LLM 管道

### LLM 客户端
- `chat(messages) -> str`：重试 timeout/429/5xx
- `chat_structured(messages, output_class) -> BaseModel`：JSON 结构化输出

### 提示词模板（从 ShopMind 提取改多租户）
- `build_system_prompt(tenant_config)`：base + system_prompt_append
- `intent_prompt(user_input, human_keywords)`：注入租户关键词
- `response_prompt(intent, context_docs, history, question)`：注入检索结果

### 意图分类器
- Layer 1 规则：human_keywords 命中 → human / 检索有结果 → faq
- Layer 2 LLM：结构化输出 `{"intent", "confidence"}`，< 阈值 → human
- 转人工：返回固定话术，不调 LLM

### chat_service（Night 3 版）
- 意图 → 检索 → LLM 生成 → 返回（无缓存/持久化）

## Night 4 — 缓存 + 多轮对话

### L1 精确缓存
- key = `{tenant_id}:{normalized_question}`，TTL 300s
- 知识变更时按租户失效

### L2 语义缓存
- key = embedding cosine similarity >= 0.85
- 按租户隔离存储

### 滑动窗口
- tiktoken 计数，max_tokens=2000，max_turns=10
- 保留最近对话，裁剪超出部分

### 对话持久化
- Conversation upsert + Message insert
- 记录 intent / cache_hit / sources_json / latency_ms

## schemas/chat.py

ChatRequest: session_id*, message*
ChatResponse: answer, intent, confidence, sources[], cache_hit(L1/L2/miss), session_id

## API

```
POST /api/v1/{tenant_slug}/chat { session_id, message } → ChatResponse
```

无需 admin 认证。session_id 首次为空时服务端生成 UUID。

## 验证

- test_intent.py: 规则匹配 + LLM 分类 + 阈值
- test_llm_client.py: 重试 + 结构化输出
- test_cache.py: L1 TTL + L2 相似度 + 失效
- test_memory.py: 滑动窗口 + token 限制
- test_chat_api.py: 完整管道端到端
- test_e2e.py: 多轮对话全链路

验收：`curl POST /api/v1/demo/chat -d '{"session_id":"","message":"退货要几天？"}'` → FAQ 答案 + sources
