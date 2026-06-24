# Pre-Push Review — 文档导入功能

| 指标 | 值 |
|------|-----|
| 日期 | 2026-06-24 16:00 |
| 分支 | master |
| 基准 | 4bc639a |
| 审查提交数 | 10 |
| 文件变更 | 19 |
| 新增行数 | 1,094 |
| 删除行数 | 0 |
| **裁决** | **FAIL** |

---

## Phase 2: 计划一致性

计划: `docs/superpowers/plans/2026-06-24-doc-import-plan.md`
规格: `docs/superpowers/specs/2026-06-24-doc-import-design.md`

| 要求 | 状态 |
|------|------|
| Document + DocumentChunk 模型 (两级存储, 级联删除) | Done |
| 5 种格式解析 (pdf/docx/xlsx/txt/md) | Done |
| 3 层分块 (结构 → LLM语义 → 固定大小兜底) | Done |
| 4 个 API 端点 (upload/list/chunks/delete) | Done |
| SHA256 去重 | Done |
| Admin 前端 Documents Tab | Done |
| 文档服务单元测试 | Done |
| API 集成测试 | Done |
| ChromaDB + BM25 双写 | Done |

**缺失/偏差:**

| # | 发现 | 严重度 |
|---|------|--------|
| 1 | 文件 >20MB 返回 **400** 而非规格要求的 **413** (Payload Too Large) | Warning |
| 2 | Embedding 失败**无重试**。规格要求逐块重试 3 次；代码只调用一次 `emb.embed()`，任何异常直接标记整份文档 failed | Warning |
| 3 | **缺少跨租户去重测试**。规格明确要求"不同租户同文件→允许" | Warning |
| 4 | 没有 pdf/docx/xlsx **解析器单元测试**，仅有 txt/md 测试 | Warning |
| 5 | **缺少检索覆盖文档分块的集成测试**（规格要求"FAQ 能命中文档中相关段落"） | Warning |

## Phase 3: 代码质量

| # | 发现 | 规则 | 严重度 |
|---|------|------|--------|
| 1 | XSS: admin UI 中 `doc.filename` 直接插入 innerHTML，未做 HTML 转义。文件名 `<img src=x onerror=alert(1)>.txt` 可在管理员浏览器执行。同文件中已存在转义模式（`renderChunks` 对 content 做了转义），未应用到 filename | Security / OWASP | Warning |
| 2 | 死代码: `parser.py` 中 `SUPPORTED_TYPES` 集合定义但从未使用 | Dead Code | Info |
| 3 | 未使用导入: `app/api/admin/document.py` 中 `Request` 导入未使用 | Dead Code | Info |

## Phase 4: 提交卫生

**PASS** — 10 个提交，全部符合 conventional commit 格式。无密钥泄露、无合并冲突标记、无超大文件。

**Info:** `.idea/` IDE 配置文件被提交，应加入 `.gitignore`。

## Phase 5: 回归测试

**PASS** — `D:/conda-envs/smart-cs/python.exe -m pytest tests/ -q`

```
92 passed, 0 failed (1 jieba deprecation warning)
```

---

## 裁决: FAIL

| 严重度 | 数量 |
|--------|------|
| Blocker | 0 |
| Warning | 7 |
| Info | 3 |

7 个 Warning ≥ 阈值 3 → **FAIL**

---

## 修复方案（按优先级排序）

| # | 问题 | 文件 | 修复 | 预计耗时 |
|---|------|------|------|----------|
| 1 | XSS: filename 未转义 | `admin-static/index.html` | 给 filename 显示位置加 `replace(/&/g,...)` 转义链 | <5min |
| 2 | >20MB 返回 400 而非 413 | `app/api/admin/document.py` | 在 upload 端点加 `len(data) > MAX_FILE_SIZE` 检查，raise 413 | <5min |
| 3 | Embedding 失败无重试 | `app/services/document_service.py` | 逐块 embed 时包 try/except，失败重试 3 次 | 15min |
| 4 | 死代码 `SUPPORTED_TYPES` | `app/core/parsing/parser.py` | 删除未使用变量，或让 API 引用它 | <5min |
| 5 | 未使用导入 `Request` | `app/api/admin/document.py` | 删除 | <5min |
| 6 | `.idea/` 被追踪 | 项目根目录 | 加入 `.gitignore` + `git rm --cached` | <5min |
| 7 | 补 pdf/docx/xlsx 解析器测试 | `tests/test_document_service.py` | 用示例二进制数据写 3 个解析测试 | 15min |
| 8 | 补跨租户去重测试 | `tests/test_document_service.py` | 同文件、不同 tenant → 允许导入 | 10min |
| 9 | 补检索覆盖分块测试 | `tests/test_document_service.py` | 导入文档 → 搜索 → 确认分块被命中 | 15min |
