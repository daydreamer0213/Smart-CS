# SmartCS 继续开发提示词

复制以下内容到新会话——

---

我正在开发 SmartCS，企业级多商户智能客服 SaaS。项目在 `D:\AAA\smart-cs\`。

## 环境

- Python: `D:/conda-envs/smart-cs/python.exe`
- conda: `D:/conda/Scripts/conda.exe`，环境 `smart-cs`
- pip 缓存: `E:/smartcs-cache/pip/`
- LLM: DeepSeek API (`deepseek-chat`)，key 在 `.env`
- Embedding: 阿里云 DashScope (`text-embedding-v3`)，key 在 `.env`

## 已完成

- **阶段 0-4**: 项目骨架、知识引擎、智能对话、前端、生产加固
- **Agent 升级**: LangGraph ReAct（search_knowledge + handoff_to_human），闲聊快路，流式 SSE
- **Phase 1.1 文档导入**: PDF/Word/Excel/Markdown 上传 → 解析 → 分块 → 嵌入 → 入库
- **94 项测试全过**，pre-push review PASS
- 项目说明书: `CLAUDE.md`

## 当前进度

Roadmap 见 `docs/planning/ROADMAP.md`：
- ✅ Phase 1.1 文档导入 — 已完成
- 🔧 Phase 1.2 JWT 认证 — 设计中，待实现
  - ✅ Spec: `docs/superpowers/specs/2026-06-24-jwt-auth-design.md`
  - ✅ Plan: `docs/superpowers/plans/2026-06-24-jwt-auth-plan.md` (10 tasks)
  - ⏳ 实现: 待启动
- ⏳ Phase 1.3 租户自助注册 — 待开发
- ⏳ Milestone 2 运维增强 — 待开发

**下一任务：执行 Phase 1.2 JWT 认证实现计划**（10 tasks，subagent-driven）

## 强制流程（重要！）

**所有开发必须走标准 skill 流程，禁止跳过 skill 直接写代码：**
1. 新功能 → `brainstorming` 出设计 → `writing-plans` 出计划 → `subagent-driven-development` 执行 → `pre-push-review` 审查
2. 修 Bug → `systematic-debugging` 先找根因再修
3. 继续项目 → `project-orchestration` → `resume-work` → `start-next-phase`

## 启动验证

```bash
D:/conda-envs/smart-cs/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/health
# → {"status":"ok","version":"0.1.0","database":"ok","chromadb":"ok"}

pytest tests/ -v   # → 94 passed

# 客服: http://127.0.0.1:8000/static/chat.html
# 管理后台: http://127.0.0.1:8000/admin/
```
