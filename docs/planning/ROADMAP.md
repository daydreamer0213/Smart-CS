# SmartCS Roadmap

## Milestone 1: 企业 HR Service Agent 基座 [status: done]
**Completed:** 2026-07-18
**Goal:** 交付可演示、可测试的企业内部 HR 知识服务 Agent 后端，而不是包装成 FAQ 聊天机器人。

### Delivered Capabilities

- [done] 文档导入：text、md、pdf、docx、xlsx 解析、分块、嵌入和后台查看。
- [done] JWT 身份边界：用户注册、登录、刷新令牌、租户与角色后端校验。
- [done] 多租户 HR 知识服务：员工只能检索本租户且符合文档受众角色的制度来源。
- [done] 混合检索与来源治理：BM25 + Vector 检索、来源返回、后端规范化合法引用。
- [done] 受限 HR Agent：知识检索、澄清、待确认转人工草稿、员工工单状态查询。
- [done] 人工处理闭环：员工确认后创建正式请求，owner/admin 指派或解决，跨租户访问返回 403。
- [done] 工程交付：Alembic 迁移、pytest 回归、隔离数据演示脚本、运行手册与面试材料。

## Milestone 2: 生产化加固 [status: pending]
**Goal:** 为真实企业接入补足身份、集成、运维和交付能力。

### Required Before Production

1. SSO/SCIM 与组织级身份生命周期。
2. 真实 HRIS、审批或工单系统适配器。
3. 通知、升级策略与 SLA 计时。
4. 端到端 tracing、业务指标、告警和审计留存策略。
5. CI/CD、镜像发布、部署加固与生产密钥治理。

### Conditional Scale Decisions

- WebSocket：仅在产品需要双向实时事件时替换或补充当前 SSE。
- Milvus：仅在 ChromaDB 的容量、并发或运维边界被实际压测证实后迁移。

## Out of Scope

SmartCS 当前是企业 AI 应用工程样板，不宣称已上线为商业 HR SaaS，也不替代完整 HRIS。
