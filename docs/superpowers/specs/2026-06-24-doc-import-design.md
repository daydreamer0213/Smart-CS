# SmartCS 文档导入设计

## 目标

支持商户上传 PDF/Word/Excel/Markdown/纯文本文件，自动解析→分块→嵌入→入库，检索时无缝覆盖手动知识条目和文档分块。

## 数据模型

新增两张表：

### Document

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| tenant_id | FK → tenants | 租户 |
| filename | str(500) | 原始文件名 |
| file_type | str(10) | pdf / docx / xlsx / txt / md |
| file_size | int | 字节数 |
| file_hash | str(64) | SHA256，同租户去重 |
| chunk_count | int | 分块数量 |
| status | str(20) | processing / ready / failed |
| error_message | str(500) | 失败原因 |
| created_at / updated_at | datetime | 时间戳 |

### DocumentChunk

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| document_id | FK → documents | 所属文档 |
| chunk_index | int | 序号 |
| content | Text | 分块文本（≤1000 字） |
| embedding_id | str | ChromaDB 文档 ID |
| token_count | int | 估算 token 数 |
| keywords | str | jieba 分词关键词，空格分隔 |
| status | str(20) | active / disabled |
| created_at / updated_at | datetime | 时间戳 |

级联删除：删 Document → 自动删所有 DocumentChunk → ChromaDB 向量 → BM25 索引。

## 导入管道

```
上传文件 → 解析文本 → 去重检查 → 分块 → 嵌入 → 双写入库
  │          │           │         │        │        │
  │      pdf→text      SHA256   结构+语义  DashScope SQL+ChromaDB
  │      docx→text                ↓
  │      xlsx→text             固定大小兜底
  │      txt/md→text
```

### 解析

| 格式 | 库 | 方法 |
|------|-----|------|
| pdf | PyMuPDF (fitz) | 提取文本层，检查是否为扫描件（无文本→失败） |
| docx | python-docx | 段落遍历 + 表格提取 |
| xlsx | openpyxl | 按行读取，第一行为列名，每行拼成 "Q: ... A: ..." |
| txt/md | 内置 | 直接读文本 |

### 分块（b+c 优先，a 兜底）

1. 按文档结构切分：md 按 `##`，docx 按标题/段落，xlsx 按行，pdf 按双换行段落
2. 每个结构块 ≤ 1000 字 → 直接作为一块；> 1000 字 → 调 DeepSeek API（项目已有）做语义边界识别切分
3. 步骤 1 无结构信息 → RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100) 兜底

### 去重

上传时算 SHA256(file_content)。同 tenant 已有相同 hash → 返回 409 "文档已导入"。

### 嵌入

分块文本调现有 DashScope text-embedding-v3 pipeline，写入 ChromaDB `{tenant_slug}_knowledge` collection（和手动知识条目共用）。

## API

```
POST   /api/v1/admin/{tenant_slug}/documents/upload
        Content-Type: multipart/form-data
        file: <binary>
        → 201 {"document_id": "uuid", "filename": "...", "chunk_count": 15, "status": "ready"}
        → 同步完成，分块嵌入全部入库后才返回 201

GET    /api/v1/admin/{tenant_slug}/documents
        ?page=1&page_size=20
        → 200 {"items": [...], "total": 5, "page": 1, "total_pages": 1}

GET    /api/v1/admin/{tenant_slug}/documents/{id}/chunks
        → 200 {"chunks": [{"index": 1, "content": "...", "token_count": 120, "status": "active"}, ...]}

DELETE /api/v1/admin/{tenant_slug}/documents/{id}
        → 级联删除 document + chunks + ChromaDB 向量 + BM25 索引
```

所有端点走 `verify_admin` 认证。

## 管理后台 UI

在 `admin-static/index.html` 知识库页面加 Tab：「文档管理」

- 上传区：拖拽/点击上传（`<input type="file" accept=".pdf,.docx,.xlsx,.txt,.md" multiple>`）
- 文档列表：文件名、格式、大小、分块数、导入时间、状态标签
- 点击文档 → 展开分块列表，可逐块查看/禁用
- 导入完成：同步处理，上传返回即 ready；如有解析失败，status 直接为 "failed"

## 错误处理

| 场景 | 响应 |
|------|------|
| 不支持的格式 | 400 "Unsupported file type: .exe" |
| 文件 > 20MB | 413 "File too large" |
| PDF 无文本层（扫描件） | status = "failed"，error_message = "PDF contains no text layer" |
| 解析异常 | status = "failed"，error_message = 异常信息前 500 字 |
| Embedding API 失败 | 逐块重试 3 次，仍失败 → document status = "failed" |
| SHA256 重复 | 409 "Document already imported" |

## 测试

| 层级 | 内容 |
|------|------|
| 单元 | 解析器各格式独立测试（pdf/docx/xlsx/txt/md） |
| 单元 | 分块策略：结构分块 / 语义切分 / 固定大小兜底 |
| 单元 | 去重检查：同 tenant 同 hash → 409，不同 tenant 同文件 → 允许 |
| 集成 | upload → 查 Document + DocumentChunk 入库 + ChromaDB 向量存在 |
| 集成 | delete → 级联删除确认 |
| 集成 | 检索覆盖文档分块：FAQ 问题能命中文档中的相关段落 |
| 回归 | 74 项现有测试全过 |

## 新依赖

```
PyMuPDF>=1.24.0       # PDF 文本提取
python-docx>=1.1.0    # Word 解析
openpyxl>=3.1.0       # Excel 解析
langchain-text-splitters>=0.3.0  # RecursiveCharacterTextSplitter 兜底分块
```
