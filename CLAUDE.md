# SmartCS 项目协作说明

## 当前定位

SmartCS 是面向 Python AI 后端、RAG 与 Agent 应用岗位的企业 HR 服务 Agent 工程样板。主线是：员工在租户和角色边界内查询制度，获得可追溯来源；制度未覆盖的例外先形成草稿，经员工确认后进入 HR 支持生命周期。

不要把项目描述成普通 FAQ 聊天机器人、通用 CRM 平台或已经商业上线的 HR SaaS。

## 维护状态

`v0.1.0` 是 2026-07-21 冻结的作品集快照。除非用户明确解除冻结，只允许：

- 复现并修复缺陷。
- 处理依赖、配置和敏感信息风险。
- 同步文档、测试、演示证据和求职材料。

M3 真实 HR/OA 工具接入和 M4 生产化加固是未来选做路线，不是当前快照的缺陷。历史 `/business/*` 仅用于 Sales Copilot Lab 回归，不扩展为 SmartCS 主线。

## 当前真实能力

- JWT 登录、刷新令牌和 `owner/admin/agent/employee` 多租户角色边界。
- 文档上传、解析、结构化分块、可选 Docling/Tesseract OCR、质量门禁、审批发布、版本/有效期和失败安全 reindex。
- 只检索当前已批准版本，并按租户与文档受众角色过滤。
- BM25 + Chroma 向量通路、来源血缘和可读中文引用。
- HR Agent Skills：制度检索、问题澄清、转人工草稿、本人请求状态。
- 员工确认后幂等建单，owner/admin 指派或解决，员工只能查看自己的请求。
- Alembic、pytest、离线评测脚本和企业流程演示脚本。

## 权威文档顺序

遇到口径冲突时按以下顺序判断：

1. 当前代码、数据库迁移和自动化测试。
2. `README.md` 与 `docs/README.md`。
3. `CONTINUE.md`。
4. `docs/planning/MILESTONE.md` 与 `docs/planning/ROADMAP.md`。
5. `docs/operations/*` 和 `docs/interview/*`。

`docs/superpowers/*` 与 `docs/pre-push-review-*` 是历史设计、计划和证据快照，只用于追溯当时决策，不代表当前运行状态。

## 本机路径

```text
项目：  D:\2026.07.09\AAA\smart-cs
Python: D:\2026.07.09\conda-envs\smart-cs\python.exe（3.12.13）
conda:  D:\2026.07.09\conda\Scripts\conda.exe
数据：  D:\DevData\smartcs
```

旧路径 `D:\AAA`、`D:\conda-envs` 和 `D:\conda` 不再使用。大型缓存、模型、OCR 数据、临时文件和本地报告必须保留在 D 盘。

## 常用命令

从仓库根目录执行：

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m pytest tests -q
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m alembic upgrade head
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8000
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' scripts\demo_enterprise_flow.py
```

离线演示可设置 `EMBEDDING_PROVIDER=hash`。该模式只证明向量链路和业务闭环可运行，不代表生产语义检索质量。

## 实现边界

- 员工演示页面是 `/static/assistant.html`，对话 API 为 `POST /api/v1/{tenant_slug}/assistant/chat`；当前不依赖 SSE 或 WebSocket。
- 后端保留 `[source:<id>]` 做机器授权校验，前端使用 `display_reply` 和 `sources.title` 呈现可读来源。
- Agent 不直接创建正式 HR 请求，只创建 `pending_handoff` 草稿；确认接口重新执行身份、租户、幂等和状态校验。
- 不在没有真实平台或沙箱时伪造“已接入 HRIS/OA”。
- 不把 HashEmbedding、固定合成语料或单机结果包装成生产准确率和 SLA。
