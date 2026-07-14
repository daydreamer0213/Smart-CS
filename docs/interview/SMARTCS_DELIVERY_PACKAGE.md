# SmartCS 求职交付包

## 项目一句话

SmartCS 是一个多租户企业员工 Agent 后端样板：员工登录后，系统按角色开放企业知识检索和 CRM Skills；AI 可以准备业务操作，但真正写入必须经过显式确认、重新校验、幂等处理和审计记录。

## 推荐简历 bullet

主 bullet：

> 独立构建多租户企业员工 Agent 后端 SmartCS，基于 FastAPI、SQLAlchemy、RAG、LangGraph、JWT 和本地 CRM demo，实现角色化知识检索、CRM 查询、业务操作草稿、确认后写入、审计日志、租户隔离和自动化测试。

可拆成 3 条：

- 构建 FastAPI 多租户企业 Agent 后端，覆盖租户、用户、角色、知识库、文档、会话、后台分析、JWT 和 API Key 管理。
- 实现企业 RAG + 角色化 Skills，支持文档导入、ChromaDB 向量检索、BM25 检索、知识可见范围控制和统一员工 Agent 入口。
- 设计受控 CRM 写操作流程，AI 只生成线索/任务操作草稿，用户确认后才写入，并支持权限复核、幂等确认、重复线索保护和审计日志。

## 30 秒讲法

SmartCS 不是普通聊天机器人，而是一个企业员工 Agent 后端样板。员工先登录，系统根据角色开放不同 Skills：普通员工只能查企业知识，销售或管理员可以查 CRM 并准备业务操作。AI 不会直接改数据，只能生成草稿，用户确认后后端才重新校验并写入，同时留下审计记录。这个项目重点展示的是企业 AI 应用落地时的权限、数据、工具调用、确认和测试闭环。

## 2 分钟讲法

我把 SmartCS 从“客服问答”收束成“企业员工 Agent”。真实企业不只关心模型能不能回答，还关心员工身份、租户隔离、角色权限、业务写操作是否可控、失败是否可追踪。

后端使用 FastAPI 和 SQLAlchemy，核心对象包括租户、用户、知识库、文档、会话、CRM 客户/线索/任务、操作草稿和审计日志。认证上有 JWT 和 API Key 两条路径，owner 可以创建租户，owner/admin 可以创建同租户用户，employee 只能使用知识 Skill，agent/admin/owner 可以使用 CRM Skill。

AI 侧保留 RAG 能力：文档导入、分块、向量检索、BM25 和后台知识治理。Agent 侧通过工具调用把知识检索和 CRM 查询接起来。对于写操作，我没有让 LLM 直接写数据库，而是设计成“生成草稿 -> 用户确认 -> 后端重新校验 -> 幂等写入 -> 审计记录”，这样更接近企业系统的安全要求。

## 企业价值

- 内部员工助手：员工查制度、流程、字段说明和企业知识。
- 销售助手：销售查询客户概览、联系人、线索、商机和跟进任务。
- 受控业务操作：AI 准备创建线索、更新线索、创建跟进任务，人确认后才写入。
- 多租户 SaaS：不同企业、部门或客户的数据和知识库互相隔离。
- AI 治理样板：展示如何把 Agent 放进可控、可测、可审计的后端系统。

## 现场演示路径

启动离线演示实例：

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

另开终端运行：

```powershell
cd D:\2026.07.09\AAA\smart-cs
$env:SMARTCS_BASE_URL="http://127.0.0.1:8000"
& D:\2026.07.09\conda-envs\smart-cs\python.exe scripts\demo_enterprise_flow.py
```

演示重点：

1. `/health` 正常，数据库和 Chroma 可用。
2. owner 注册租户。
3. owner 创建 agent 和 employee。
4. agent 访问后台被拒，说明角色边界生效。
5. owner 创建企业知识并上传文档。
6. employee 调用统一 `/assistant/chat`，只拿到知识 Skill。
7. 后台查看知识、文档、分析。
8. 跨租户访问被拒。
9. 打开 `/static/assistant.html` 展示单一员工 Agent UI。

## 当前边界

- 这不是已经上线运营的商业 SaaS，而是求职用工程样板。
- 本地 CRM 使用 fictional SQLite demo data，不是通用 CRM 集成平台。
- 离线 hash embedding 用于稳定演示，不代表生产 embedding 质量。
- 完整回答质量取决于真实 LLM / embedding 配置和业务文档质量。
- 旧 `/chat` 和 `/business` 路由保留为兼容和测试用途，主展示入口是 `/assistant`。

## 相关文档

- `README.md`：项目总览。
- `docs/interview/SMARTCS_FINAL_PITCH.md`：最终简历和面试表达稿。
- `docs/interview/SMARTCS_INTERVIEW.md`：面试深聊话术。
- `docs/interview/SMARTCS_DEMO_SCRIPT.md`：3 分钟现场演示稿。
- `scripts/demo_enterprise_flow.py`：可运行演示脚本。
