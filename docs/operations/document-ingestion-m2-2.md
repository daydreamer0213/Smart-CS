# M2-2 高级文档解析验收

M2-2 保留 M2-1 基线不变，另建结构化基准测试，覆盖 `parse_structured_file` 与 `chunk_document`。结构化报告只用于仓库内合成 HR 语料的验收，不是通用解析准确率声明。

## 安装

使用 `D:\2026.07.09\conda-envs\smart-cs\python.exe`，按 [Docling 与 Tesseract 配置](docling-ocr-setup.md) 安装可选依赖，并确认 `chi_sim` 与 `eng` 语言包可用。

解析临时目录、Docling 模型、Hugging Face/Torch 缓存、Tesseract 和 tessdata 都必须位于 `D:\DevData\smartcs`。应用启动与结构化基准脚本会应用相同配置；无需手动设置 `TEMP` 或 `TMP`。基准 JSON 保存到 `D:\DevData\smartcs\benchmarks`，不得提交。

## 运行

在仓库根目录依次执行。省略 `--mode` 时仍使用 M2-1 基础解析器和分块器。

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' scripts\benchmark_document_ingestion.py `
    --fixture-dir tests\fixtures\documents `
    --output 'D:\DevData\smartcs\benchmarks\m2-1-baseline-after-m2-2.json' `
    --environment-label local-cpu

& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' scripts\benchmark_document_ingestion.py `
    --mode structured `
    --fixture-dir tests\fixtures\documents `
    --output 'D:\DevData\smartcs\benchmarks\m2-2-structured.json' `
    --environment-label local-cpu
```

Docling 进度和稀疏页面的 Tesseract 方向警告可能出现在控制台。是否可发布以 JSON 质量门禁为准，不以控制台无警告为准。结构化模式先写报告，再在门禁失败时返回非零退出码；基础模式保留历史零退出行为。

## 查看结果

```powershell
$baseline = Get-Content -Raw 'D:\DevData\smartcs\benchmarks\m2-1-baseline-after-m2-2.json' | ConvertFrom-Json
$structured = Get-Content -Raw 'D:\DevData\smartcs\benchmarks\m2-2-structured.json' | ConvertFrom-Json
$baseline.summary
$structured.summary
$structured.results | Select-Object id, status, route, route_reason, indexable, elapsed_ms
```

只有语料、解析事实、分块事实、来源血缘和总验收门禁全部为 `passed`，M2-2 才通过。报告记录：

- 解析路由和受控路由原因。
- 解析器、分块器名称与版本。
- 质量状态、警告与指标。
- 元素和分块的页码、章节路径、元素类型与 source index。
- facts 的元素/分块证据、表格关联、阅读顺序、可索引状态和耗时。
- Python、依赖、Docling、Tesseract、CPU、平台、manifest hash 和 Git 上下文，不包含本地路径、用户名、凭据或原始异常文本。

加密语料必须保持 `blocked`、`indexable: false`、无 chunks，并且只返回 `encrypted_input` 与 `missing_page_coverage` 两个质量警告。未声明的额外警告会使语料验收失败；意外解析异常统一返回 `Document processing failed.`。

## 已验证证据

2026-07-19 在 Windows 10 AMD64、6 逻辑 CPU 环境验证：

- M2-1：9 个语料，7 个成功、2 个错误，命中 16/18 facts（88.89%），语料耗时合计 0.57 秒。
- M2-2：8 个成功、1 个加密语料被阻止，解析 facts 18/18、分块 facts 18/18，所有 provenance 与验收门禁通过，语料耗时合计 16.15 秒。
- Manifest SHA-256：`68ccf288d79b83803b8c87162f21880f45095c40557b22223e9c035b0c734869`。
- Python 3.12.13、PyMuPDF 1.27.2.3、python-docx 1.2.0、openpyxl 3.1.5、docling-slim 2.113.0、Tesseract 5.5.2。
- 年假表格在同一表格元素和 chunk 中保留“工龄/年假天数”表头关系以及“20年以上/15天”行关系。
- 双栏语料保持 manifest 声明的阅读顺序；PDF、带标题 DOCX、多 Sheet XLSX 的页码和章节来源血缘通过。

## 演示路径

通过文档管理 API 上传干净 PDF、扫描 PDF、表格和加密语料；查看解析路由、质量状态以及页码/章节来源；检索通过的制度并展示页码引用；最后证明加密文档没有可搜索 chunks，也不会进入员工知识检索。

业务价值是完整性控制：混合或扫描制度不会在只解析到部分文本时静默发布，从而避免回答遗漏 OCR 页面内容却仍显得权威。

## 限制

- 9 个文档均为合成语料，18/18 是确定性语料门禁，不是生产或通用 OCR 准确率。
- CPU OCR 的延迟和识别结果可能随硬件、Tesseract 版本、线程调度与方向检测变化；依赖或硬件改变后需重跑。
- M2-3/M2-4 已补充人工复核、内容寻址原件、审批发布、原子切换当前版本和失败安全 reindex。
- Chroma 与 BM25 仍是独立外部索引；孤儿数据对账与持久重试属于 M4，而不是本阶段已交付能力。
- M2-5 是独立的 curated retrieval gate，见 [M2-5 RAG 检索评测](rag-evaluation-m2-5.md)。
- 在 M4 可靠性、可观测、部署和恢复完成前，不宣称生产就绪。
