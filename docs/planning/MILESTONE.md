# Milestone 1: 生产就绪

**Status:** active
**Started:** 2026-06-24

## Goal

补全商户接入必需功能：文档导入、JWT 认证、自助注册。让 SmartCS 从技术 demo 变成可交付的 SaaS 产品。

## Definition of Done

- [ ] PDF/Word 文档上传后自动解析、分块、嵌入、入库，商户可在管理后台查看导入结果
- [ ] JWT 认证替换 API Key，支持用户注册和登录
- [ ] 租户自助注册页面，注册后自动创建 ChromaDB collection 和默认配置
- [ ] 所有新功能有 pytest 测试覆盖（>= 80%）
- [ ] pre-push review PASS
- [ ] 74 项现有测试全过，无回归

## Phases

1. Phase 1.1 — 文档导入 [active]
2. Phase 1.2 — JWT 认证 [pending]
3. Phase 1.3 — 租户自助注册 [pending]
