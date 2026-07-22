# SmartCS 里程碑状态

**当前状态：** `v0.1.0` 求职作品集快照已于 2026-07-21 冻结

里程碑 1 已完成企业 HR 服务 Agent 基座；里程碑 2 已完成文档智能、知识治理与可量化检索评测。`v0.1.0` 标签冻结验收为 `403 passed, 4 skipped`；2026-07-22 当前 `main` 维护回归为 `405 passed, 4 skipped`。M3 真实 HR 工具接入和 M4 生产化加固是解冻后的选做路线，不在本快照范围内，也不视为当前缺陷。

## 里程碑 2：文档智能与知识治理

**状态：** 已交付
**完成日期：** 2026-07-19

### 完成定义

- [x] M2-2 parser gate：9 个 fixture、8 个解析成功、1 个加密 PDF 阻止索引；18/18 parsed facts、18/18 chunk facts 与 provenance 通过。
- [x] M2-3 质量门禁：低质量文档进入人工复核，不静默发布。
- [x] M2-4 治理生命周期：原件留存、审批发布、当前版本、有效期、失败安全 reindex 与来源血缘。
- [x] M2-5 retrieval gate：8 个已索引 fixture、11 个 curated facts-only chunks、12 条 golden queries、`top_k=3`；Recall@3 `11/12 = 91.67%`、MRR `91.67%`、已召回来源 provenance `100%`，门禁通过。
- [x] 多租户与受众角色过滤继续经过真实 SQL 检索边界验证；加密 fixture 未进入索引。
- [x] 运行数据和报告位于 `D:\DevData\smartcs`，不写入 `C:`。

**口径与限制：** M2-2 证明固定合成语料的解析与分块验收；CPU Docling/OCR 在当前内存压力下可波动。M2-5 是 curated source-chunk 的确定性检索回归，不是通用 PDF/OCR 准确率或生产 SLA。HashEmbedding 非语义；本次 BM25 贡献 11、vector 贡献 0，因此不声称混合语义检索质量。唯一失败 query 为 `payroll-contact`。

**可复现命令和报告字段：** [M2-5 RAG 评测运行手册](../operations/rag-evaluation-m2-5.md)。

## 里程碑 1：企业 HR 服务 Agent 基座

**状态：** 已完成
**完成日期：** 2026-07-18

### 目标

完成可交付的企业内部 HR 知识服务 Agent 后端：身份先行、知识有受众、回答可溯源、例外可转人工、状态可治理。

### 完成定义

- [x] 文档上传后完成解析、分块、嵌入和入库，后台可查看导入结果。
- [x] JWT 注册、登录和刷新令牌替换旧 API Key 身份边界。
- [x] 租户与角色在后端校验；跨租户 HR 支持接口拒绝访问。
- [x] 员工只能检索角色可见的制度文档，回答返回授权来源和规范化引用。
- [x] Agent 可创建待确认转人工草稿；确认后形成正式 HR 支持请求。
- [x] owner/admin 可查看、指派和解决请求；员工只能查看本人状态。
- [x] Alembic 可初始化全新数据库，pytest 回归覆盖关键边界，演示脚本覆盖完整生命周期。

### 范围边界

本里程碑不包含真实 HRIS/OA 工具适配、SSO/SCIM、通知 SLA、生产级 tracing/metrics、CI/CD 和生产密钥治理；M2 文档智能与知识治理已由后续 Milestone 2 交付。

## 冻结待办

项目未明确解冻前不进入新里程碑。解冻后可评估 Milestone 3 的单一真实 HR/OA 工具接入，再按真实试点需要评估 Milestone 4。WebSocket 和 Milvus 仅在实际规模需求出现后考虑，不作为当前项目的伪需求。
