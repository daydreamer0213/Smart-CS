# 本地 HR Agent 演示手册

## Goal

在不污染日常开发数据的前提下，运行一个虚构北辰科技租户的 SmartCS 实时演示，依次验证制度文档导入、审批发布、带来源引用的回答、失败安全 reindex、待确认转人工、HR 处理生命周期和跨租户拒绝。此演示需要可调用的模型与 embedding 配置。

## Prerequisites

- 项目位于 `D:\2026.07.09\AAA\smart-cs`。
- 使用 `D:\2026.07.09\conda-envs\smart-cs\python.exe`。
- `.env` 提供 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`、`EMBEDDING_API_KEY`、`EMBEDDING_BASE_URL` 和 `EMBEDDING_MODEL`，但不要打印、提交或截图这些值。
- 临时数据库、Chroma 和日志写入 `D:\DevData\smartcs-demo`；上传原件写入 `D:\DevData\smartcs\demo-documents`，避免占用系统盘。
- `alembic upgrade head` 是全新数据库的受支持初始化路径。

## Terminal One

```powershell
cd D:\2026.07.09\AAA\smart-cs
$demoRoot = "D:/DevData/smartcs-demo/" + (Get-Date -Format "yyyyMMdd-HHmmss")
New-Item -ItemType Directory -Force -Path $demoRoot | Out-Null
$env:DATABASE_URL = "sqlite:///$demoRoot/smartcs-demo.db"
$env:CHROMA_PERSIST_DIR = "$demoRoot/chroma"
$env:LOG_DIR = "$demoRoot/logs"
$env:DOCUMENT_STORAGE_DIR = "D:/DevData/smartcs/demo-documents"
& D:\2026.07.09\conda-envs\smart-cs\python.exe -m alembic upgrade head
& D:\2026.07.09\conda-envs\smart-cs\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

保持该终端运行。`alembic upgrade head` 仅支持在线初始化全新数据库；不要把离线 SQL 输出当作本项目的全新库初始化流程。

## Terminal Two

在服务已经启动后，另开终端运行：

```powershell
cd D:\2026.07.09\AAA\smart-cs
$env:SMARTCS_BASE_URL = "http://127.0.0.1:8000"
& D:\2026.07.09\conda-envs\smart-cs\python.exe scripts\demo_enterprise_flow.py
```

脚本在运行时生成虚构用户与临时凭据，输出仅包含状态、租户、文档 family、业务版本、索引代次、来源和工单 ID，不应输出 JWT、密钥、密码、`storage_key` 或物理文件路径。

## Observable Success Criteria

- `/health` 返回 `200`。
- 北辰科技租户及 owner、HR admin、employee 创建成功。
- employee 受众的年假文档上传后为 `ready + pending_review`，此时尚不可被员工检索。
- owner 审批后文档为 `approved + current`，员工检索才放行。
- employee 的制度回答在 `reply` 中保留授权校验所需的 `[source:<id>]`，`display_reply` 显示 `来源：《北辰科技年假制度》`，员工界面不展示裸 ID。
- reindex 成功创建下一 `index_generation` 并保持 `ready + current`；失败时上一 current generation 不变。
- 海外派驻例外请求返回 `pending_handoff`，员工确认后形成 `open` 工单。
- HR admin 将工单依次更新为 `assigned`、`resolved`；employee 在 `/hr-support/me` 看到 `resolved`。
- employee 使用 A 租户 JWT 访问 B 租户 HR 接口返回 `403`。
- 脚本以 `Live HR Agent demo complete.` 结束且退出码为 `0`。

`503` 表示模型、提供方、网络或额度失败，脚本必须以非零退出码结束；它不是一个可接受的成功结果。

## Troubleshooting

| 现象 | 排查方式 |
| --- | --- |
| Cannot reach SmartCS | 确认终端一的 Uvicorn 仍在 `127.0.0.1:8000` 监听，再检查 `SMARTCS_BASE_URL`。不要在工单或截图中粘贴任何密钥、JWT、密码或 `.env` 内容。 |
| `503` | 检查 `.env` 中的模型与 embedding 配置是否存在、网络是否可达、提供方额度是否可用；`503` 不是成功演示。不要在工单或截图中粘贴任何密钥、JWT、密码或 `.env` 内容。 |
| 文档导入失败 | 查看 Uvicorn 中与文件类型、解析或 Chroma 相关的错误，并确认临时目录可写；重新创建新的 `$demoRoot`。不要在工单或截图中粘贴任何密钥、JWT、密码或 `.env` 内容。 |
| 缺少来源引用 | 确认上传返回 `ready`、审批返回 `approved + current`、文档受众包含 `employee`，并检查实时模型调用是否完成；不要手工伪造引用。不要在工单或截图中粘贴任何密钥、JWT、密码或 `.env` 内容。 |
| reindex 返回 `failed` | 查看公开的安全错误和解析质量状态；上一 approved/current 版本仍应可查询。底层异常只在脱敏日志中排查。 |
| 迁移失败 | 使用终端一中的在线 `alembic upgrade head` 路径，检查 `$demoRoot` 写权限并保留完整迁移错误文本（去除任何敏感配置）。不要在工单或截图中粘贴任何密钥、JWT、密码或 `.env` 内容。 |
