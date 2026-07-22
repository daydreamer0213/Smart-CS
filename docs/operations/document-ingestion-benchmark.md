# M2-1 文档导入基线测试

## 用途

该命令使用仓库内的合成 HR 文档测量 SmartCS 基础解析器，并记录已知失败。它是后续解析改进的固定对照点，不是通用 PDF 准确率，也不代表生产文档效果。

## 运行

从仓库根目录执行：

```powershell
New-Item -ItemType Directory -Force 'D:\DevData\smartcs\benchmarks' | Out-Null
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' scripts/benchmark_document_ingestion.py --fixture-dir tests/fixtures/documents --output 'D:\DevData\smartcs\benchmarks\m2-1-baseline.json' --environment-label local-cpu
```

JSON 报告保存在 `D:\DevData\smartcs\benchmarks`，属于本地生成物，不提交到 Git。

## 结果解释

- `parsed` 只表示基础解析器返回了文本，不代表页面布局、阅读顺序、表格或来源结构正确。
- `fact_recall` 是合成语料中必需事实的精确文本命中率，不是通用准确率。
- 固定基线包含 9 个语料：7 个解析成功、2 个错误、18 个必需事实中命中 16 个，总体为 88.89%。
- 扫描 PDF 没有文本层，基础模式不含 OCR，因此返回错误；加密 PDF 因没有解密流程而返回错误。
- 混合文本与扫描页的 PDF 可能只提取文本页，遗漏图片页事实；基线会记录这种不完整结果。
- 表格和双栏语料用于暴露结构问题；返回 `parsed` 不代表保留了表格关系或可靠阅读顺序。
- 这些差距用于定义 M2-2 的改进范围，不能与 M2-2 高级解析结果混用。

## 运行上下文

`run_context` 用于比较本地报告，但不记录敏感信息。它包含环境标签、manifest schema 与 SHA-256、尽力获取的 Git revision、Python 和操作系统版本、PyMuPDF、python-docx、openpyxl，以及 `CHUNK_SIZE`、`CHUNK_OVERLAP`、`MAX_CHUNK_SIZE`。

`--environment-label` 使用 `local-cpu` 之类的简短非敏感值；默认值为 `local-unspecified`。报告不写入环境变量、凭据、用户名或绝对工作目录。每个语料只记录 manifest 中声明的合成 facts，不写出完整 chunk 文本。

## 数据边界

只运行仓库内已提交的合成测试语料。不要提交本地报告、真实企业文档或所谓“脱敏后的”企业材料。
