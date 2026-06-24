# SmartCS 阶段 1 — 知识库引擎设计

## 目标

实现管理后台知识库 CRUD + 混合检索管道（ChromaDB 向量 + BM25 关键词 + RRF 融合）。两晚连续交付。

## 架构总览

```
第 1 晚（CRUD 管理层）
├── schemas/knowledge.py      ← Pydantic 请求/响应模型
├── services/knowledge_service.py ← SQL 操作层（第 1 晚不碰向量）
├── api/admin/auth.py         ← API Key 验证独立模块
├── api/admin/knowledge.py    ← CRUD 端点（分页+搜索+分类筛选）
└── tests/test_admin_knowledge_api.py

第 2 晚（检索管道层）
├── core/embedding/           ← NEW: embedding 抽象
│   ├── base.py               ← ABC: embed(texts) -> vectors
│   ├── openai_provider.py    ← text-embedding-3-small
│   └── bge_provider.py       ← BAAI/bge-large-zh-v1.5 本地
├── core/retrieval/vector_store.py  ← ChromaDB 按租户 collection
├── core/retrieval/bm25_index.py    ← BM25 按租户内存索引
├── core/retrieval/fusion.py        ← RRF 融合
├── services/knowledge_service.py   ← 补全：CRUD 同步 ChromaDB + BM25
└── tests/test_retrieval.py + test_embedding.py
```

## 关键设计决策

| 决策 | 选择 | 说明 |
|------|------|------|
| embedding 提供方 | 可切换 (openai / bge) | 统一 BaseEmbeddingProvider 抽象，config 控制 |
| SQL ↔ ChromaDB 一致性 | 先写 SQL，再写向量，失败回滚 SQL | 保证不出现孤儿向量 |
| 知识删除策略 | 软删除 (→ archived) | 保留 embedding_id 引用，不物理删除 |
| BM25 索引更新 | 全量重建 | 数据量小，简单可靠；后续数据量大后改增量 |
| ChromaDB collection 命名 | `{tenant_slug}_knowledge` | 与阶段 0 约定一致 |

## config 新增字段

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `embedding_provider` | `openai` | `openai` 或 `bge` |
| `embedding_api_key` | (空) | provider=openai 时必填 |
| `embedding_model` | `text-embedding-3-small` | OpenAI 或 BGE 模型名 |

## embedding 抽象

```python
class BaseEmbeddingProvider(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    @property
    @abstractmethod
    def dim(self) -> int: ...
```

Factory: `get_embedding_provider(settings) -> BaseEmbeddingProvider`

## schemas

- `KnowledgeCreate`: question*, answer*, keywords?, category_id?
- `KnowledgeUpdate`: 全 optional + status (active/draft/archived)
- `KnowledgeItemResponse`: 完整字段 + created_at/updated_at (ISO str)
- `KnowledgeListParams`: page(1), page_size(20, max100), q?, category_id?, status?
- `KnowledgeListResponse`: items[], total, page, page_size, total_pages
- `CategoryCreate/Update/Response`: name, description, sort_order

## API 端点

```
GET    /api/v1/admin/{slug}/knowledge        列表 (分页+搜索+筛选)
POST   /api/v1/admin/{slug}/knowledge        新增
GET    /api/v1/admin/{slug}/knowledge/{id}   详情
PUT    /api/v1/admin/{slug}/knowledge/{id}   编辑 (partial update)
DELETE /api/v1/admin/{slug}/knowledge/{id}   归档 (软删除)
POST   /api/v1/admin/{slug}/knowledge/batch  批量导入 [{question, answer, ...}]
GET    /api/v1/admin/{slug}/categories       分类列表
POST   /api/v1/admin/{slug}/categories       新增分类
```

每个端点: `Depends(verify_admin) + Depends(get_db) + get_tenant(db, slug)`

## 检索管道

### VectorStore
- `get_collection(tenant_slug)`: get_or_create `{slug}_knowledge`
- `add(tenant_slug, doc_id, embedding)`, `update(...)`, `delete(...)`
- `search(tenant_slug, embedding, top_k=5)`: `collection.query()`

### BM25IndexManager
- `build(tenant_slug, corpus)`: jieba 分词 → `BM25Okapi`
- `search(tenant_slug, query, top_k=5)`: `get_scores()` → sorted
- `add/remove`: 增量重建（阶段 1 全量重建）

### RRF fusion
```
RRF(d) = sum(1 / (k + rank_i(d)) for each ranker i)
k=60, top_k=5
输入: [(doc_id, distance/score), ...] from vector + bm25
输出: [{"doc_id", "score", "sources": ["vector", "bm25"]}, ...]
```

## knowledge_service 双写流程

```
create:
  1. SQL INSERT → knowledge_items
  2. embedding = embed(question + " " + answer)
  3. vector_store.add(slug, item.id, embedding)
  4. bm25_index.add(slug, item.id, question)
  失败回滚 SQL → db.rollback()

update:
  1. SQL UPDATE
  2. 如果 question/answer 变了 → 重 embedding → vector_store.update
  → bm25_index 重建

delete:
  1. SQL: status = "archived"
  2. vector_store.delete(slug, item.id)
  → bm25_index 重建
```

## 验证

1. `pytest tests/ -v` 全部通过
2. `POST /api/v1/admin/demo/knowledge` 创建条目 → ChromaDB 检索到
3. `GET /api/v1/admin/demo/knowledge?q=xxx` 模糊搜索正确
4. 两个租户的知识条目 ChromaDB collection 级别隔离
5. BM25 + vector RRF 融合返回合理结果
