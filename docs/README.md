# SmartCS 中文文档导航

本页区分当前有效文档与历史快照。项目事实以当前代码、数据库迁移和自动化测试为最终依据。

## 当前有效文档

- [项目首页与快速开始](../README.md)：项目定位、能力、架构、环境、测试和演示入口。
- [项目接手说明](../CONTINUE.md)：供后续任务快速恢复上下文。
- [项目协作说明](../CLAUDE.md)：冻结规则、权威文档顺序和实现边界。
- [里程碑状态](planning/MILESTONE.md)：已经交付的能力和冻结范围。
- [项目路线图](planning/ROADMAP.md)：已完成 M1/M2，以及解冻后可选的 M3/M4。

## 运行与验收

- [本地 HR Agent 演示](operations/local-hr-agent-demo.md)
- [M2-5 RAG 检索评测](operations/rag-evaluation-m2-5.md)
- [Docling 与 Tesseract 配置](operations/docling-ocr-setup.md)
- [M2-1 文档导入基线](operations/document-ingestion-benchmark.md)
- [M2-2 高级文档解析验收](operations/document-ingestion-m2-2.md)
- [FastGPT 有界 PoC 记录](operations/fastgpt-poc-runbook.md)

## 求职材料

- [3 分钟演示稿](interview/SMARTCS_DEMO_SCRIPT.md)
- [面试深聊要点](interview/SMARTCS_INTERVIEW.md)
- [求职交付包](interview/SMARTCS_DELIVERY_PACKAGE.md)
- [最终项目表达稿](interview/SMARTCS_FINAL_PITCH.md)

## 历史资料

`docs/superpowers/*` 保存各阶段的设计和实施计划，`docs/pre-push-review-*` 保存早期审查结果。它们是不可改写的历史快照，可能包含旧 CRM 定位、旧路径、旧接口或当时尚未完成的任务，只用于追溯决策，不作为当前运行说明。

## 术语约定

- **机器引用**：后端回答中的 `[source:<id>]`，用于来源授权校验。
- **可读引用**：员工界面中的 `来源：《制度名称》`，不显示裸 UUID。
- **文档家族**：同一业务制度的多版本集合，名称用于业务展示。
- **索引代次**：同一业务版本重新解析、分块和索引后的技术代次。
- **质量门禁**：将解析结果划分为通过、需复核或失败，未通过内容不静默发布。
- **转人工草稿**：Agent 生成但尚未成为正式 HR 支持请求的待确认对象。
