# Milestone 1: 企业 HR Service Agent 基座

**Status:** done
**Completed:** 2026-07-18

## Goal

完成可交付的企业内部 HR 知识服务 Agent 后端：身份先行、知识有受众、回答可溯源、例外可转人工、状态可治理。

## Definition of Done

- [x] 文档上传后完成解析、分块、嵌入和入库，后台可查看导入结果。
- [x] JWT 注册、登录和刷新令牌替换旧 API Key 身份边界。
- [x] 租户与角色在后端校验；跨租户 HR 支持接口拒绝访问。
- [x] 员工只能检索角色可见的制度文档，回答返回授权来源和规范化引用。
- [x] Agent 可创建待确认转人工草稿；确认后形成正式 HR 支持请求。
- [x] owner/admin 可查看、指派和解决请求；员工只能查看本人状态。
- [x] Alembic 可初始化全新数据库，pytest 回归覆盖关键边界，演示脚本覆盖完整生命周期。

## Scope Boundary

本里程碑不包含 SSO/SCIM、真实 HRIS 或工单系统适配、通知 SLA、生产级 tracing/metrics、CI/CD 和生产密钥治理；这些属于生产化加固阶段。

## Next Milestone

Milestone 2 聚焦真实企业系统接入与生产运维能力。WebSocket 和 Milvus 仅在实际规模需求出现后评估，不作为当前项目的伪需求。
