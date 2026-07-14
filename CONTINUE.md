# SmartCS Continue Prompt

复制给新会话使用。

---

你正在继续开发 SmartCS。请使用中文，直接务实。

## 项目定位

SmartCS 不是普通 FAQ 聊天机器人，也不再只包装成“智能客服后台”。当前定位是：

> 多租户企业员工 Agent 后端样板：员工登录后，根据角色获得企业知识检索、CRM 查询、业务操作草稿和确认后写入能力。

它服务郭铭福求职，重点证明：

- Python AI 后端工程能力。
- RAG / 文档导入 / 知识治理。
- Agent 工具调用和角色化 Skill 暴露。
- JWT / API Key 多租户身份边界。
- 受控 CRM 写操作：先生成草稿，用户显式确认后才写入。
- 审计日志、幂等确认、错误处理和测试覆盖。

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

大文件和依赖缓存放 D 盘：

```text
D:\2026.07.09\smartcs-cache\pip
D:\2026.07.09\smartcs-cache\huggingface
D:\2026.07.09\smartcs-cache\torch
```

## 当前状态

已完成：

- 新电脑环境恢复，依赖和缓存路径整理到 D 盘。
- JWT 登录、多租户身份边界、owner/admin/agent/employee 角色。
- 企业知识库 RAG：文档导入、分块、ChromaDB、BM25、后台治理。
- 统一员工 Agent 入口：`/api/v1/{tenant_slug}/assistant/*`。
- 角色化 Skills：
  - `employee`：企业知识检索。
  - `agent/admin/owner`：企业知识检索 + CRM 查询 + 业务操作草稿。
- 本地 CRM MVP：客户概览、线索/任务操作草稿、显式确认、幂等确认、审计日志、重复线索保护。
- 旧 `/chat` 和 `/business` 路由保留为兼容和回归测试用途，主展示入口是 `/assistant`。
- 离线 `hash` embedding provider，用于无外部额度时稳定演示。
- README、求职交付包、最终面试表达稿和 3 分钟演示稿。

## 核心文件

- `README.md`
- `docs/interview/SMARTCS_DELIVERY_PACKAGE.md`
- `docs/interview/SMARTCS_FINAL_PITCH.md`
- `docs/interview/SMARTCS_INTERVIEW.md`
- `docs/interview/SMARTCS_DEMO_SCRIPT.md`
- `scripts/demo_enterprise_flow.py`
- `app/api/auth.py`
- `app/api/assistant.py`
- `app/api/business.py`
- `app/core/agent/business_agent.py`
- `app/services/assistant_service.py`
- `app/services/business_service.py`
- `app/models/user.py`
- `app/models/crm.py`
- `app/core/embedding/hash_provider.py`
- `tests/test_auth.py`
- `tests/test_assistant_api.py`
- `tests/test_assistant_agent.py`
- `tests/test_business_api.py`

## 常用命令

```powershell
cd D:\2026.07.09\AAA\smart-cs

D:\2026.07.09\conda-envs\smart-cs\python.exe -m pytest tests/ -v

D:\2026.07.09\conda-envs\smart-cs\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

D:\2026.07.09\conda-envs\smart-cs\python.exe scripts\demo_enterprise_flow.py
```

离线演示建议使用临时数据库和临时 Chroma 目录：

```powershell
$demoRoot="D:/2026.07.09/smartcs-cache/demo-" + (Get-Date -Format "yyyyMMdd-HHmmss")
New-Item -ItemType Directory -Force -Path $demoRoot | Out-Null
$env:EMBEDDING_PROVIDER="hash"
$env:DATABASE_URL="sqlite:///$demoRoot/smartcs-demo.db"
$env:CHROMA_PERSIST_DIR="$demoRoot/chroma"
$env:LOG_DIR="$demoRoot/logs"
```

## 求职讲法

一句话：

> SmartCS 是一个多租户企业员工 Agent 后端，员工登录后按角色获得企业知识和 CRM Skills，AI 可以准备业务操作，但写入必须显式确认、重新校验并留下审计。

不要夸大：

- 不是已经商业上线的 SaaS。
- 离线 hash embedding 只是演示稳定性方案，不代表生产向量质量。
- 本地 CRM 是 fictional demo data，不是通用 CRM 集成平台。
- UI 不是主卖点，主卖点是 Python AI 后端、RAG、Agent、权限边界、受控写操作和测试。

## 下一步建议

阶段性开发已收口。下一步只做投递和展示准备：

1. 按 `docs/interview/SMARTCS_FINAL_PITCH.md` 选择目标岗位版本的简历 bullet。
2. 按 `docs/interview/SMARTCS_DEMO_SCRIPT.md` 练 3 分钟演示。
3. 如需上传 GitHub，先确认是否公开展示；公开前检查 `.env`、数据库、日志和缓存不要入库。
