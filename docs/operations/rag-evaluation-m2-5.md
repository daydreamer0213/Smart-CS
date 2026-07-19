# M2-5 RAG 检索评测运行手册

## 用途与边界

本手册运行的是 M2-5 检索回归门禁，不是 PDF 解析压测。它使用已审核的 curated retrieval corpus，通过真实的治理 SQL、Chroma、BM25、RRF 和 `search_knowledge` 边界，检查固定 HR 问题的 source-chunk 检索与来源溯源。

M2-2 parser gate 与本门禁分开：它的历史成功报告为 9 个 fixture、8 个解析成功、1 个加密 PDF 阻止索引、18/18 parsed facts、18/18 chunk facts 与 provenance 通过。CPU Docling/OCR 在当前内存压力下可波动，因此不要把每次 M2-5 回归变成重新解析整套 PDF 的前置条件。

M2-5 不调用 FastGPT、LLM 或 LLM judge。离线 `HashEmbedding` 仅验证向量通路，属于非语义 embedding；它不能证明混合语义检索质量。

## 运行命令

在项目根目录执行。所有运行时数据库、Chroma 数据和报告都写入 `D:\DevData\smartcs`，不写入 `C:`。

```powershell
cd D:\2026.07.09\AAA\smart-cs

& D:\2026.07.09\conda-envs\smart-cs\python.exe scripts\evaluate_rag_retrieval.py `
  --fixture-dir tests\fixtures\documents `
  --work-dir D:\DevData\smartcs\rag-eval\m2-5 `
  --output D:\DevData\smartcs\benchmarks\m2-5-rag-evaluation.json `
  --environment-label local-windows-cpu
```

若只需检查已有报告，可读取 `D:\DevData\smartcs\benchmarks\m2-5-rag-evaluation.json`；报告不应提交到 Git。

## 已记录验收结果

| 字段 | 值 |
| --- | --- |
| indexed fixtures | 8 |
| curated facts-only source chunks | 11 |
| golden queries | 12 |
| top_k | 3 |
| Recall@3 | 11/12 = 91.67% |
| MRR | 91.67% |
| recalled-source provenance accuracy | 100% |
| gate | passed |
| failed query | `payroll-contact` |
| BM25 contribution | 11 query hits |
| vector contribution | 0 query hits |

`payroll-contact` 保留为失败样本：它的中文提问与唯一受信邮箱事实缺少词法重合，BM25 未命中，而非语义 HashEmbedding 也没有提供语义补偿。不要通过改题、补造关键词或把 vector 通路表述成语义效果来掩盖该结果。

## 报告字段

- `run_context`：Python、平台、环境标签与三份 manifest 的哈希，用于确认语料和运行环境。
- `corpus`：语料来源、已索引 fixture 数、chunk 数和加密 fixture 排除情况。
- `query_count`、`retriever_profile.top_k`：评测规模与检索截断值。
- `results`：仅包含 query ID、命中 rank 和允许的 retriever 名称，不含正文、绝对 fixture 路径或凭据。
- `failed_query_ids`：未在 `top_k` 内找到预期 source chunk 的问题；它是定位入口，不应静默删除。
- `retriever_contributions`：BM25 与 vector 在命中 query 上的贡献统计，不能用“完整检索栈已加载”替代实际贡献。
- `summary`：`recall_at_k`、`mrr`、`provenance_accuracy` 和 `gate`。provenance 的分母是已召回 source chunks，Recall 单独负责未召回问题。

## 失败排查

1. `gate=failed`：先检查 `failed_query_ids`、对应 rank 和 retriever；确认 manifest、curated corpus 与报告哈希一致，不要先改阈值或 golden query。
2. provenance 失败：检查 source chunk ID、文件标题、fact 文本、页码/section/sheet 元数据与 golden manifest 的绑定。不要用宽页码范围掩盖错误引用。
3. BM25 或 vector 贡献异常：先确认同一环境下的 corpus、治理 SQL、approved/current 状态、tenant 和 audience role；HashEmbedding 的 vector 命中为 0 不是语义模型退化的证据。
4. 工作目录被拒绝：Windows 下 `--work-dir` 和 `--output` 必须位于 `D:\DevData\smartcs` 内。目录不存在时可先用 `New-Item -ItemType Directory -Force` 创建。
5. Chroma 文件被占用或下次运行无法清理：先确认没有并发评测进程。当前关闭逻辑会调用 Chroma 私有的 `vector_store._client._system.stop()` 来释放 Windows 句柄；`chromadb` 升级后该内部 API 可能变化，升级依赖时必须重跑 M2-5 回归并检查清理行为。

## 求职转化

**简历 bullet：** 构建 HR 知识库 RAG 的分层质量门禁：解析层覆盖 OCR/结构化分块/来源元数据，检索层以 12 条 golden queries 验证 Recall@3、MRR、来源溯源及多租户受众边界，并保留失败 query 定位证据。

**面试讲法：** 我把“文档是否被正确理解”和“员工问题是否能检索到正确来源”拆成两个门禁。M2-2 负责 parser gate，M2-5 直接走治理检索边界；当前 11/12 命中是 BM25 的真实贡献，HashEmbedding 只验证向量管道，因此不会把它包装成生产语义检索。

**可演示路径：** 运行命令 -> 打开 `summary`、`retriever_contributions`、`failed_query_ids` -> 解释 `payroll-contact` 为什么保留失败 -> 回到已审批制度问答，展示页级来源和受控转人工。

## 非生产声明

该报告是合成、curated source-chunk 的离线回归证据，不代表通用 PDF/OCR 准确率、真实企业语料效果或生产 SLA。真实语义 embedding、真实 HR 工具接入、异步处理、监控、SSO 与 SLA 分别属于后续 M3/M4 范围。
