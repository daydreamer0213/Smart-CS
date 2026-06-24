# SmartCS Roadmap

## Milestone 1: 生产就绪 [status: active]
**Started:** 2026-06-24
**Goal:** 补全商户接入必需功能，从"能用"到"好用"

### Phase 1.1: 文档导入 [status: active]
**Goal:** 支持上传 PDF/Word，自动解析→分块→嵌入→入库
**Surface:** Backend
**Plan:** `docs/superpowers/plans/YYYY-MM-DD-doc-import.md`

### Phase 1.2: JWT 认证 [status: pending]
**Goal:** 替换 API Key 为 JWT，加用户注册/登录
**Surface:** Backend

### Phase 1.3: 租户自助注册 [status: pending]
**Goal:** 注册页面 + 自动创建 ChromaDB collection + 初始化租户配置
**Surface:** UI

## Milestone 2: 运维增强 [status: pending]
**Goal:** 生产级运维能力，持续交付 + 规模化扩展

### Phase 2.1: CI/CD [status: pending]
**Goal:** GitHub Actions 自动化测试 + Docker 镜像构建推送
**Surface:** Infra

### Phase 2.2: WebSocket 实时对话 [status: pending]
**Goal:** 双向 WebSocket 通信替代 SSE 单向流
**Surface:** Backend

### Phase 2.3: Milvus 升级 [status: pending]
**Goal:** ChromaDB → Milvus 向量数据库迁移
**Surface:** Data
