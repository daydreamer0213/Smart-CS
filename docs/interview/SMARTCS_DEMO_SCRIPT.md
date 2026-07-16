# SmartCS 3 分钟演示稿

## 演示定位

SmartCS 不是普通 FAQ 聊天机器人，而是一个企业员工 Agent 后端样板：

- 多租户企业知识库。
- RAG 文档导入和知识治理。
- 员工登录后的统一 Agent 入口。
- 按角色开放知识 / CRM Skills。
- CRM 写操作先生成草稿，确认后才写入。
- JWT / API Key 身份边界。
- 后台管理、审计和自动化测试。

一句话讲法：

> 这个项目证明我能把 Agent 放进企业后端工程里：员工先认证，Agent 按角色拿到工具，业务写入必须确认并审计。

## 演示命令

启动一个不污染正式数据的离线演示实例：

```powershell
cd D:\2026.07.09\AAA\smart-cs

$demoRoot="D:/2026.07.09/smartcs-cache/demo-" + (Get-Date -Format "yyyyMMdd-HHmmss")
New-Item -ItemType Directory -Force -Path $demoRoot | Out-Null
$env:EMBEDDING_PROVIDER="hash"
$env:DATABASE_URL="sqlite:///$demoRoot/smartcs-demo.db"
$env:CHROMA_PERSIST_DIR="$demoRoot/chroma"
$env:LOG_DIR="$demoRoot/logs"

& D:\2026.07.09\conda-envs\smart-cs\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

另开一个终端运行：

```powershell
cd D:\2026.07.09\AAA\smart-cs
$env:SMARTCS_BASE_URL="http://127.0.0.1:8000"
& D:\2026.07.09\conda-envs\smart-cs\python.exe scripts\demo_enterprise_flow.py
```

也可以打开：

```text
http://127.0.0.1:8000/static/assistant.html
```

## 讲解顺序

1. 先看 `/health`，说明服务、数据库、Chroma 都正常。
2. 注册 owner，owner 创建一个新租户。
3. owner 创建 agent 和 employee，说明这是租户内员工身份管理。
4. agent 访问后台被拒，说明业务角色不等于后台管理员。
5. owner 创建企业知识，说明知识不是写死在 prompt 里。
6. 上传文档，看到 `status=ready` 和 `chunk_count=1`。
7. employee 调用 `/assistant/chat`，说明统一员工 Agent 入口存在。
8. 看 `enabled_skills`，说明普通员工只拿到知识 Skill。
9. 查看后台知识、文档、分析接口。
10. 用 A 租户 token 访问 B 租户后台被拒，说明租户边界生效。

如果现场要讲 CRM 能力：

> CRM 相关能力不是让 LLM 直接改库，而是先生成待确认草稿。用户确认时，后端重新校验权限、处理幂等键、写入数据并记录审计日志。

## 面试讲法

可以这样讲：

> 我重点演示的不是回答文案有多华丽，而是企业 Agent 必须具备的工程闭环。这里员工先认证，后端根据角色开放 Skills；普通员工只能查知识，销售或管理员才能查 CRM 和准备业务操作。写操作不会由 LLM 直接执行，而是先生成草稿，确认后再由后端写入并审计。

如果面试官追问“企业价值是什么”，回答：

> 企业真正关心的是 AI 能不能安全接入内部知识和业务系统。SmartCS 覆盖了租户隔离、角色权限、知识治理、工具调用、确认后写入、审计日志和测试验证，这些是 Agent 从 demo 走向企业应用时绕不开的部分。

## 最新本地演示关注点

```text
owner register: 201
agent creation: 201
employee creation: 201
agent admin access: 403
knowledge creation: 201
document upload: 201, status=ready, chunk_count=1
assistant route: 200 when LLM is configured, 503 is acceptable when LLM key is absent
knowledge/documents/analytics backend views: 200
cross-tenant admin access: 403
```

## 边界说明

- 离线 hash embedding 只是为了稳定演示，不代表生产 embedding 质量。
- 本地 CRM 是 fictional demo data，不是完整 CRM 产品。
- 如果 `.env` 没有真实 LLM key，assistant 路由会返回可读的 503；角色和安全边界由测试覆盖。
- 主展示入口是 `/assistant`；旧 `/chat` 已下线，`/business` 仅保留 JWT 保护的受控写入过渡接口。
