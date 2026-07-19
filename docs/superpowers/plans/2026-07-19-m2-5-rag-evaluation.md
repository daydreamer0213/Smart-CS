# M2-5 RAG Retrieval Evaluation Delivery Record

**Status:** delivered on 2026-07-19

## Goal

为 SmartCS 建立可重复、无 LLM judge 的检索回归门禁，并把可测量的结果转化为运行、面试和演示材料。

## Final Layered Architecture

M2-5 不再把解析与检索混在一次执行中。

1. **Parser gate（M2-2）**：固定合成语料通过 Docling/Tesseract、结构化分块与来源断言。历史成功报告为 9 fixtures、8 parsed、1 encrypted blocked、18/18 parsed facts、18/18 chunk facts 和 provenance passed。CPU Docling/OCR 在当前内存压力下可能波动，因此它是独立解析验收，不是每次检索回归的前置步骤。
2. **Curated retrieval gate（M2-5）**：从受信 manifest facts 构造 11 个 facts-only source chunks，将 8 个可索引 fixture 写入隔离的 SQLite/Chroma/BM25 运行空间，再由真实 `search_knowledge`、治理 SQL、RRF 边界执行 12 条 golden queries。
3. **Evidence contract**：报告仅输出 query ID、rank、retriever 名称、聚合指标、失败 query 和安全运行元数据；不输出正文、凭据或绝对 fixture 路径。

HashEmbedding 只提供稳定、离线的向量通路；它不是语义 embedding。评测不调用 FastGPT、LLM 或 LLM judge。

## Constraints

- [x] 提交语料为合成数据，不含企业私密文档。
- [x] 运行数据库、Chroma 与报告位于 `D:\DevData\smartcs`，不占用 `C:`。
- [x] 加密 fixture 不进入索引。
- [x] 门禁阈值为 Recall@3 `>= 0.90` 且 recalled-source provenance `== 1.00`。
- [x] 多租户和受众角色边界经过真实 SQL 检索入口验证。

## Completed Work

- [x] 建立 12 条 golden-query manifest，绑定稳定 source chunk、fixture、受信 fact 与来源元数据。
- [x] 建立 metrics contract：Recall@3、MRR、recalled-source provenance、failed query IDs、gate 和 retriever contributions。
- [x] 用 11 个 curated facts-only chunks 取代每次运行 Docling 的耦合流程，避免检索回归受 CPU 解析内存波动影响。
- [x] 复用真实治理 SQL、Chroma、BM25、RRF 和 `search_knowledge`，而不是在评测内另写检索逻辑。
- [x] 验证路径、标签、清理、全局检索状态恢复、报告脱敏和错误路径。
- [x] 完成操作手册、README、路线图、里程碑、交接说明、设计说明和面试演示稿统一。

## Acceptance Record

报告路径：`D:\DevData\smartcs\benchmarks\m2-5-rag-evaluation.json`

| Metric | Result |
| --- | --- |
| indexed fixtures | 8 |
| curated facts-only chunks | 11 |
| golden queries / top_k | 12 / 3 |
| Recall@3 | 11/12 = 91.67% |
| MRR | 91.67% |
| recalled-source provenance | 100% |
| gate | passed |
| failed query | `payroll-contact` |
| BM25 / vector contribution | 11 / 0 |

`payroll-contact` 的中文问题与唯一受信邮箱事实没有词法重合，因而未由 BM25 召回；非语义 HashEmbedding 同样没有命中。保留该失败项，不通过改 query 或虚构关键词获得虚假的 100%。

## Reproduction

```powershell
cd D:\2026.07.09\AAA\smart-cs
& D:\2026.07.09\conda-envs\smart-cs\python.exe scripts\evaluate_rag_retrieval.py --fixture-dir tests\fixtures\documents --work-dir D:\DevData\smartcs\rag-eval\m2-5 --output D:\DevData\smartcs\benchmarks\m2-5-rag-evaluation.json --environment-label local-windows-cpu
```

完整字段、失败排查和 Chroma 关闭风险见 [M2-5 RAG 评测运行手册](../../operations/rag-evaluation-m2-5.md)。

## Scope and Next Milestones

这份结果只证明 curated source-chunk 回归门禁，不代表通用 PDF/OCR 准确率、混合语义检索质量或生产 SLA。

- M3 pending：只接入一个真实 HR/OA 平台或沙箱，完成年假余额、本人工单、确认后请假草稿、组织/HR 联系人查询。
- M4 pending：异步导入、失败重试和重新索引、审计/监控/通知/SLA、企业身份与部署加固。
