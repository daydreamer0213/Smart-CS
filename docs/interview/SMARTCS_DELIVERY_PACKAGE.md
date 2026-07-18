# SmartCS 求职交付包

## 一句话定位

SmartCS 是面向企业内部员工的多租户 HR 服务 Agent 后端工程样板：以 JWT、受众文档检索、来源引用、员工确认和 HR 支持生命周期，把制度问答放进可治理的服务闭环。

## 推荐简历 bullet

- 构建 FastAPI 多租户 HR 服务 Agent 后端，完成 JWT 租户边界、角色化文档权限、文档导入及 BM25 + 向量检索的制度问答。
- 将例外处理设计为“Agent 草稿、员工确认、幂等建单、HR 指派/解决、员工查状态”的受控生命周期，避免模型直接变更业务状态。
- 为认证、隔离、受众、检索降级和转人工生命周期补充 pytest 回归，并交付基于虚构数据的本地实时演示脚本。

## 可展示的企业价值

- **员工自助**：员工查询年假、报销、入职等制度时得到可追溯来源，而非无依据回答。
- **例外收口**：制度未覆盖或员工要求人工时，系统把问题交给 HR 队列，而不是编造规则。
- **治理边界**：租户、角色与文档受众在后端校验，跨租户访问被拒绝。
- **可运营状态**：员工能看到自己的请求，HR 能指派和解决，状态变化可审计。

## 现场演示路线

1. 运行 `/health`，确认服务返回 `200`。
2. 创建虚构北辰科技租户及 owner、HR admin、employee 身份。
3. 上传 employee 受众的年假制度文档。
4. employee 得到带 `[source:<id>]` 的制度回答。
5. employee 提出海外派驻例外，看到 `pending_handoff` 草稿。
6. employee 确认后得到 `open` 的正式请求。
7. HR admin 指派并解决；employee 在 `/hr-support/me` 查看 `resolved`。
8. A 租户 employee 访问 B 租户接口得到 `403`。

详细命令见：[本地 HR Agent 演示手册](../operations/local-hr-agent-demo.md)。模型返回 `503` 时，演示必须视为失败并排查配置、网络或额度。

## 项目边界

- 当前目标是企业 AI 应用工程证明，不是完整 HRIS 或商业 SaaS。
- 未实现 SSO/SCIM、真实 HRIS/工单系统适配、通知与 SLA、生产 tracing/metrics、CI/CD 与生产密钥治理。
- `/business/*` 仅是保留用于历史回归覆盖的 Sales Copilot Lab，不是主路径或面试主卖点。

## 交付材料

- [项目总览](../../README.md)
- [3 分钟演示稿](SMARTCS_DEMO_SCRIPT.md)
- [面试深聊要点](SMARTCS_INTERVIEW.md)
- [最终项目表达稿](SMARTCS_FINAL_PITCH.md)
- [本地 HR Agent 演示手册](../operations/local-hr-agent-demo.md)
