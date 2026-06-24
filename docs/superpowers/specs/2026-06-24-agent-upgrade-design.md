# SmartCS Agent 升级设计

## 目标

将当前传统 RAG 管道升级为 LangGraph 驱动的智能体架构，使客服能自主决策：查知识库、转人工、直接回答，而非固定流水线拼接。

## 架构对比

### 当前（传统 RAG 管道）

```
用户消息 → L1缓存 → L2缓存 → 检索 → 意图分类 → LLM生成 → 响应
```

所有路径固定，LLM 被动接收检索结果来拼答案。无法多步推理，无法自主判断何时转人工。

### 升级后（Agent 循环）

```
用户消息 → [L1快速缓存路径]
              ↓
         Agent 节点（LLM + 工具调用）
          ↕              ↕
    search_knowledge  handoff_to_human
          ↕              ↕
        回到 Agent → 决定回复 → END
```

LLM 从"根据检索结果生成答案"变成"自主决定下一步做什么"——是检索知识库、转人工，还是基于自身知识直接回答。

## LangGraph 状态图

```
START → agent → [条件路由]
                   ├─ 调用工具 → tools → agent（循环）
                   └─ 直接回复 → END
```

### 节点

| 节点 | 职责 |
|------|------|
| `agent` | LLM + 工具定义 + system prompt。决定调用哪个工具还是直接输出回复内容 |
| `tools` | 执行实际工具调用（search_knowledge / handoff_to_human），把结果以 tool role 消息追加到历史，回到 agent |

### 边

- `agent → tools`：条件边，当 LLM 返回 `tool_calls` 时触发
- `agent → END`：条件边，当 LLM 返回普通文本回复时触发
- `tools → agent`：固定边，工具执行完总是回到 agent 继续推理

## 工具清单（v1）

### search_knowledge

- **参数**: `query: str` — 自然语言搜索词
- **返回**: `list[{question, answer, score, doc_id}]` — 匹配的知识条目列表
- **实现**: 复用现有 retrieval pipeline（embedding → BM25+向量 → RRF fusion → DB enrich）
- **Agent 使用方式**: LLM 决定需要检索时，传入用户问题作为 query；得到结果后自行判断相关性并组织回答

### handoff_to_human

- **参数**: `reason: str` — 需要转人工的原因摘要
- **返回**: `{success: bool, message: str}` — 确认消息
- **实现**: 写入 Conversation 状态（status → handed_off + handoff_reason），返回安抚话术让 agent 转述
- **Agent 使用方式**: LLM 判断问题超出能力范围时主动调用；也可在 search_knowledge 无结果后调用

## 状态定义

```python
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]  # 消息历史（含 tool calls/results），自动管理滑动窗口
    tenant_id: str                            # 当前租户 ID
    session_id: str                           # 对话 session
    final_answer: str | None                  # 最终回复，流式输出完成后设置
    handoff: bool                             # 是否已转人工
```

`add_messages` reducer 自动合并新消息到历史列表，避免重复。LangGraph checkpoint 持久化会话状态（SQLite 后端），不再需要手写的 tiktoken 截断（deepseek-chat 64K 上下文窗口足够容纳多轮对话，后续如需控制 token 上限可在 agent node 内加截断逻辑）。

## 模块迁移计划

### 保留不改

| 模块 | 说明 |
|------|------|
| `models/` | 6 张表结构不变 |
| `api/deps.py` | DB session + 租户注入不变 |
| `api/admin/` | 管理后台全部端点不变 |
| `config.py` | 增加 agent 相关字段，其余不变 |
| `middleware/` | logging / tenant / ratelimit / error_handler 全部不变 |
| `core/cache/exact.py` | L1 精确缓存不变，在进入 agent 前做快速路径 |
| `core/cache/semantic.py` | L2 语义缓存保留，在进入 agent 前做快速路径 |
| `core/retrieval/` | vector_store / bm25_index / fusion 全部不变，封装为工具调用 |
| `core/embedding/` | 不变 |

### 改造

| 模块 | 改动 |
|------|------|
| `services/chat_service.py` | 486 行手写管道 → 替换为 LangGraph agent 调用，约 100 行 |
| `core/llm/client.py` | `chat()` 加 `tools` 参数；`chat_stream()` 保留但 agent 流式走 LangGraph astream_events |
| `api/chat.py` | SSE 端点改用 LangGraph astream_events 推送 token |
| `core/conversation/memory.py` | 可删除，滑动窗口由 LangGraph add_messages + checkpoint 接管 |
| `schemas/chat.py` | ChatResponse 加 `handoff: bool` 字段 |

### 删除

| 模块 | 原因 |
|------|------|
| `core/intent/classifier.py` | LLM tool calling 天然覆盖意图判断 |
| `core/intent/__init__.py` | 同上 |

### 新增

| 文件 | 说明 |
|------|------|
| `app/core/agent/__init__.py` | Agent 模块入口 |
| `app/core/agent/graph.py` | LangGraph 状态图定义（build_graph） |
| `app/core/agent/state.py` | AgentState TypedDict |
| `app/core/agent/tools.py` | 工具函数定义（search_knowledge, handoff_to_human） |

## 流式输出策略

LangGraph 的 `astream_events` API 可以在 agent 执行过程中按事件推送：

1. `on_tool_start` → SSE `{type: "tool_start", data: {tool: "search_knowledge"}}`
2. `on_tool_end` → SSE `{type: "tool_end", data: {tool: "search_knowledge", result: ...}}`
3. `on_chat_model_stream` → SSE `{type: "delta", data: token}`
4. 图结束 → SSE `{type: "done", data: ChatResponse}`

前端 JS 增加 `tool_start` / `tool_end` 事件处理，可显示"正在搜索知识库..."过渡状态。

## 错误处理

- 工具调用异常：捕获后转成 tool role error 消息返回 agent，让 LLM 决定如何回复
- LLM API 重试：继承现有 3 次指数退避
- 图循环保护：`recursion_limit=10`（最多 5 轮工具调用）
- 超时保护：agent 总超时 60s，单次 LLM 调用 30s

## 测试策略

| 层级 | 测试内容 |
|------|----------|
| 单元测试 | 工具函数独立测试（search 返回结果/空列表，handoff 写 DB） |
| 集成测试 | agent graph 用 fixture LLM 执行，验证路由逻辑（调工具 vs 直接回复） |
| 端到端 | 多轮对话用例（查知识库→回复，查不到→转人工） |
| 回归 | 43 项现有测试全部保持通过，改造不破旧 API |

迁移期间增加 `tests/test_agent.py` 新增 agent 层测试，`tests/test_tools.py` 覆盖两个工具函数。

## 配置新增

```python
# config.py 新增字段
agent_recursion_limit: int = 10      # agent 最大循环次数
agent_timeout_seconds: int = 60      # agent 总超时
agent_stream_enabled: bool = True    # 是否启用流式（开发可关）
```

## 新依赖

```
langgraph>=0.2.0        # Agent 状态图编排
langgraph-checkpoint-sqlite>=2.0.0  # checkpoint 持久化到 SQLite
```

## 不分阶段，一次性交付

以下是一次性交付的范围：

1. LangGraph graph + AgentState + 2 个工具
2. `chat_service.py` 重写，接入 agent
3. `api/chat.py` 改造流式 SSE 推送
4. 前端 JS 增加工具调用过渡态
5. 删除 intent classifier + conversation memory
6. L1/L2 缓存快速路径（agent 前）
7. 测试（agent 单元 + 集成 + 回归现有 43 项）
8. config 新增字段
