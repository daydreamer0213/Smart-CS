# SmartCS Phase 1 — Knowledge Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Build admin knowledge CRUD API (Night 1) + hybrid retrieval pipeline with ChromaDB/BM25/RRF (Night 2).

**Architecture:** Night 1 fills schemas → knowledge_service (SQL only) → auth module → CRUD endpoints. Night 2 adds embedding abstraction layer → ChromaDB vector store → BM25 index → RRF fusion → dual-write completion in knowledge_service.

**Tech Stack:** FastAPI + SQLAlchemy + ChromaDB + BM25Okapi + RRF + OpenAI/BGE embedding + jieba

## Global Constraints

- Python 3.12, conda env `smart-cs`, conda at `D:\conda\Scripts\conda.exe`
- All routes under `/api/v1/admin/{tenant_slug}/...` with `verify_admin` dependency
- Knowledge deletion is soft-delete (status → "archived"), not physical
- ChromaDB collection naming: `{tenant_slug}_knowledge`
- SQL → ChromaDB dual-write: SQL first, then vector; failure triggers SQL rollback
- BM25 index: full rebuild per tenant on knowledge change
- Embedding provider switchable via `Settings.embedding_provider`

---

### Task 0: Install sentence-transformers

- [ ] **Step 1: Install**

```bash
D:\conda\Scripts\conda.exe run -n smart-cs pip install sentence-transformers
```

- [ ] **Step 2: Verify**

```bash
D:\conda\Scripts\conda.exe run -n smart-cs python -c "from sentence_transformers import SentenceTransformer; print('OK')"
```

---

### Task 1: Fill schemas/knowledge.py

**Files:** Modify `app/schemas/knowledge.py`

**Produces:** `KnowledgeCreate`, `KnowledgeUpdate`, `KnowledgeItemResponse`, `KnowledgeListParams`, `KnowledgeListResponse`, `CategoryCreate`, `CategoryUpdate`, `CategoryResponse`

- [ ] **Step 1: Write schema file**

```python
"""Knowledge base CRUD schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class KnowledgeCreate(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    answer: str = Field(..., min_length=1, max_length=5000)
    keywords: str | None = Field(None, max_length=500)
    category_id: str | None = None


class KnowledgeUpdate(BaseModel):
    question: str | None = Field(None, min_length=1, max_length=2000)
    answer: str | None = Field(None, min_length=1, max_length=5000)
    keywords: str | None = Field(None, max_length=500)
    category_id: str | None = None
    status: Literal["active", "draft", "archived"] | None = None


class KnowledgeItemResponse(BaseModel):
    id: str
    tenant_id: str
    category_id: str | None
    question: str
    answer: str
    keywords: str | None
    embedding_id: str | None
    status: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class KnowledgeListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    q: str | None = None
    category_id: str | None = None
    status: Literal["active", "draft", "archived"] | None = None


class KnowledgeListResponse(BaseModel):
    items: list[KnowledgeItemResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=1000)
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    sort_order: int | None = None


class CategoryResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: str
    sort_order: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Verify import**

```bash
D:\conda\Scripts\conda.exe run -n smart-cs python -c "import sys; sys.path.insert(0,'D:/AAA/smart-cs'); from app.schemas.knowledge import KnowledgeCreate, KnowledgeUpdate, KnowledgeListParams, KnowledgeListResponse, CategoryCreate, CategoryResponse; print('OK')"
```

---

### Task 2: services/knowledge_service.py — SQL-only CRUD

**Files:** Modify `app/services/knowledge_service.py`

**Produces:** `create_knowledge(db, tenant_id, data) -> KnowledgeItem`, `update_knowledge(db, item_id, data) -> KnowledgeItem | None`, `delete_knowledge(db, item_id) -> KnowledgeItem | None`, `get_knowledge(db, item_id) -> KnowledgeItem | None`, `list_knowledge(db, tenant_id, params) -> tuple[list, int]`, `create_category(db, tenant_id, data) -> Category`, `list_categories(db, tenant_id) -> list[Category]`

- [ ] **Step 1: Write knowledge_service.py**

```python
"""Knowledge base service — SQL CRUD. Phase 2 adds vector sync."""

from sqlalchemy.orm import Session

from app.models.knowledge import Category, KnowledgeItem
from app.schemas.knowledge import (
    CategoryCreate,
    KnowledgeCreate,
    KnowledgeListParams,
    KnowledgeUpdate,
)


def create_knowledge(db: Session, tenant_id: str, data: KnowledgeCreate) -> KnowledgeItem:
    item = KnowledgeItem(
        tenant_id=tenant_id,
        category_id=data.category_id,
        question=data.question,
        answer=data.answer,
        keywords=data.keywords or "",
        status="active",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_knowledge(db: Session, item_id: str, data: KnowledgeUpdate) -> KnowledgeItem | None:
    item = db.query(KnowledgeItem).filter(KnowledgeItem.id == item_id).first()
    if item is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


def delete_knowledge(db: Session, item_id: str) -> KnowledgeItem | None:
    item = db.query(KnowledgeItem).filter(KnowledgeItem.id == item_id).first()
    if item is None:
        return None
    item.status = "archived"
    db.commit()
    db.refresh(item)
    return item


def get_knowledge(db: Session, item_id: str) -> KnowledgeItem | None:
    return db.query(KnowledgeItem).filter(KnowledgeItem.id == item_id).first()


def list_knowledge(
    db: Session, tenant_id: str, params: KnowledgeListParams
) -> tuple[list[KnowledgeItem], int]:
    query = db.query(KnowledgeItem).filter(
        KnowledgeItem.tenant_id == tenant_id,
        KnowledgeItem.status != "archived",
    )
    if params.q:
        like = f"%{params.q}%"
        query = query.filter(
            KnowledgeItem.question.ilike(like) | KnowledgeItem.keywords.ilike(like)
        )
    if params.category_id:
        query = query.filter(KnowledgeItem.category_id == params.category_id)
    if params.status:
        query = query.filter(KnowledgeItem.status == params.status)

    total = query.count()
    items = (
        query.order_by(KnowledgeItem.updated_at.desc())
        .offset((params.page - 1) * params.page_size)
        .limit(params.page_size)
        .all()
    )
    return items, total


def create_category(db: Session, tenant_id: str, data: CategoryCreate) -> Category:
    cat = Category(
        tenant_id=tenant_id,
        name=data.name,
        description=data.description or "",
        sort_order=data.sort_order or 0,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def list_categories(db: Session, tenant_id: str) -> list[Category]:
    return (
        db.query(Category)
        .filter(Category.tenant_id == tenant_id)
        .order_by(Category.sort_order.asc())
        .all()
    )
```

- [ ] **Step 2: Verify import**

```bash
D:\conda\Scripts\conda.exe run -n smart-cs python -c "import sys; sys.path.insert(0,'D:/AAA/smart-cs'); from app.services.knowledge_service import create_knowledge, list_knowledge; print('OK')"
```

---

### Task 3: api/admin/auth.py + Update deps.py

**Files:** Modify `app/api/admin/auth.py`, Modify `app/api/deps.py`

- [ ] **Step 1: Write auth.py**

```python
"""Admin API key authentication."""

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.tenant import AdminApiKey

router = APIRouter()


def verify_admin(request: Request, db: Session = Depends(get_db)) -> AdminApiKey:
    key = request.headers.get("X-Admin-Key", "")
    if not key:
        raise HTTPException(status_code=401, detail="Missing X-Admin-Key header")

    key_hash = hashlib.sha256(key.encode()).hexdigest()
    api_key = db.query(AdminApiKey).filter(AdminApiKey.key_hash == key_hash).first()
    if api_key is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return api_key
```

- [ ] **Step 2: Update deps.py — remove verify_admin, re-export from auth**

Final deps.py:
```python
"""FastAPI dependency injection."""

from collections.abc import Generator

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.admin.auth import verify_admin  # noqa: F401
from app.db import SessionLocal
from app.models.tenant import Tenant


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_tenant(db: Session, tenant_slug: str) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_slug}' does not exist")
    return tenant
```

- [ ] **Step 3: Verify imports**

```bash
D:\conda\Scripts\conda.exe run -n smart-cs python -c "import sys; sys.path.insert(0,'D:/AAA/smart-cs'); from app.api.admin.auth import verify_admin; from app.api.deps import get_db, get_tenant; print('OK')"
```

---

### Task 4: api/admin/knowledge.py — CRUD Endpoints

**Files:** Modify `app/api/admin/knowledge.py`

- [ ] **Step 1: Write full CRUD endpoints**

```python
"""Admin knowledge base CRUD."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.admin.auth import verify_admin
from app.api.deps import get_db, get_tenant
from app.models.tenant import AdminApiKey, Tenant
from app.schemas.knowledge import (
    CategoryCreate,
    CategoryResponse,
    KnowledgeCreate,
    KnowledgeItemResponse,
    KnowledgeListParams,
    KnowledgeListResponse,
    KnowledgeUpdate,
)
from app.services import knowledge_service

router = APIRouter()


def _fmt_iso(dt) -> str:
    return dt.isoformat() if dt else ""


def _item_to_response(item) -> KnowledgeItemResponse:
    return KnowledgeItemResponse(
        id=item.id, tenant_id=item.tenant_id, category_id=item.category_id,
        question=item.question, answer=item.answer, keywords=item.keywords,
        embedding_id=item.embedding_id, status=item.status,
        created_at=_fmt_iso(item.created_at), updated_at=_fmt_iso(item.updated_at),
    )


@router.get("/api/v1/admin/{tenant_slug}/knowledge")
async def list_knowledge(
    tenant_slug: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None),
    category_id: str | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    _admin: AdminApiKey = Depends(verify_admin),
):
    params = KnowledgeListParams(page=page, page_size=page_size, q=q, category_id=category_id, status=status)
    items, total = knowledge_service.list_knowledge(db, tenant.id, params)
    return KnowledgeListResponse(
        items=[_item_to_response(it) for it in items],
        total=total, page=params.page, page_size=params.page_size,
        total_pages=max(1, (total + params.page_size - 1) // params.page_size),
    )


@router.post("/api/v1/admin/{tenant_slug}/knowledge", status_code=201)
async def create_knowledge(
    tenant_slug: str, body: KnowledgeCreate,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    _admin: AdminApiKey = Depends(verify_admin),
):
    item = knowledge_service.create_knowledge(db, tenant.id, body)
    return _item_to_response(item)


@router.get("/api/v1/admin/{tenant_slug}/knowledge/{item_id}")
async def get_knowledge(
    tenant_slug: str, item_id: str,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    _admin: AdminApiKey = Depends(verify_admin),
):
    item = knowledge_service.get_knowledge(db, item_id)
    if item is None or item.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    return _item_to_response(item)


@router.put("/api/v1/admin/{tenant_slug}/knowledge/{item_id}")
async def update_knowledge(
    tenant_slug: str, item_id: str, body: KnowledgeUpdate,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    _admin: AdminApiKey = Depends(verify_admin),
):
    item = knowledge_service.get_knowledge(db, item_id)
    if item is None or item.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    updated = knowledge_service.update_knowledge(db, item_id, body)
    return _item_to_response(updated)


@router.delete("/api/v1/admin/{tenant_slug}/knowledge/{item_id}")
async def delete_knowledge(
    tenant_slug: str, item_id: str,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    _admin: AdminApiKey = Depends(verify_admin),
):
    item = knowledge_service.get_knowledge(db, item_id)
    if item is None or item.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    knowledge_service.delete_knowledge(db, item_id)
    return {"status": "archived"}


@router.post("/api/v1/admin/{tenant_slug}/knowledge/batch", status_code=201)
async def batch_import(
    tenant_slug: str, body: list[KnowledgeCreate],
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    _admin: AdminApiKey = Depends(verify_admin),
):
    items = []
    for data in body:
        item = knowledge_service.create_knowledge(db, tenant.id, data)
        items.append(_item_to_response(item))
    return {"imported": len(items), "items": items}


@router.get("/api/v1/admin/{tenant_slug}/categories")
async def list_categories(
    tenant_slug: str,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    _admin: AdminApiKey = Depends(verify_admin),
):
    cats = knowledge_service.list_categories(db, tenant.id)
    return [
        CategoryResponse(
            id=c.id, tenant_id=c.tenant_id, name=c.name,
            description=c.description or "", sort_order=c.sort_order,
            created_at=_fmt_iso(c.created_at), updated_at=_fmt_iso(c.updated_at),
        )
        for c in cats
    ]


@router.post("/api/v1/admin/{tenant_slug}/categories", status_code=201)
async def create_category(
    tenant_slug: str, body: CategoryCreate,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    _admin: AdminApiKey = Depends(verify_admin),
):
    cat = knowledge_service.create_category(db, tenant.id, body)
    return CategoryResponse(
        id=cat.id, tenant_id=cat.tenant_id, name=cat.name,
        description=cat.description or "", sort_order=cat.sort_order,
        created_at=_fmt_iso(cat.created_at), updated_at=_fmt_iso(cat.updated_at),
    )
```

- [ ] **Step 2: Verify imports**

```bash
D:\conda\Scripts\conda.exe run -n smart-cs python -c "import sys; sys.path.insert(0,'D:/AAA/smart-cs'); from app.api.admin.knowledge import router; print('OK')"
```

---

### Task 5: tests/test_admin_knowledge_api.py — Night 1 Integration Tests

**Files:** Modify `tests/conftest.py` (add admin fixtures), Modify `tests/test_admin_knowledge_api.py`

- [ ] **Step 1: Add admin fixtures to conftest.py**

Append these lines at end of `tests/conftest.py`:
```python
import hashlib
from app.models.tenant import AdminApiKey


@pytest.fixture
def admin_api_key(db: Session, test_tenant: Tenant) -> tuple[str, AdminApiKey]:
    raw_key = "test-admin-key-123"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = AdminApiKey(tenant_id=test_tenant.id, key_hash=key_hash, label="test-key")
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    return raw_key, api_key


@pytest_asyncio.fixture
async def admin_client(app, engine, db, admin_api_key):
    raw_key, _ = admin_api_key
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers={"X-Admin-Key": raw_key}) as ac:
        yield ac
```

- [ ] **Step 2: Write test_admin_knowledge_api.py**

```python
"""Admin knowledge CRUD API tests."""


async def test_create_knowledge(admin_client, test_tenant):
    response = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/knowledge",
        json={"question": "How to return?", "answer": "Return within 7 days"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["question"] == "How to return?"
    assert data["status"] == "active"
    assert "id" in data


async def test_list_knowledge_empty(admin_client, test_tenant):
    response = await admin_client.get(f"/api/v1/admin/{test_tenant.slug}/knowledge")
    assert response.status_code == 200
    assert response.json()["total"] == 0


async def test_list_knowledge_with_items(admin_client, test_tenant):
    for i in range(3):
        await admin_client.post(
            f"/api/v1/admin/{test_tenant.slug}/knowledge",
            json={"question": f"Q{i}?", "answer": f"A{i}"},
        )
    response = await admin_client.get(f"/api/v1/admin/{test_tenant.slug}/knowledge")
    assert response.status_code == 200
    assert response.json()["total"] == 3


async def test_list_knowledge_pagination(admin_client, test_tenant):
    for i in range(25):
        await admin_client.post(
            f"/api/v1/admin/{test_tenant.slug}/knowledge",
            json={"question": f"Q{i}?", "answer": f"A{i}"},
        )
    response = await admin_client.get(f"/api/v1/admin/{test_tenant.slug}/knowledge?page_size=10&page=2")
    data = response.json()
    assert data["page"] == 2
    assert len(data["items"]) == 10


async def test_list_knowledge_search(admin_client, test_tenant):
    await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/knowledge",
        json={"question": "Return policy?", "answer": "7 days", "keywords": "return,refund"},
    )
    await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/knowledge",
        json={"question": "Shipping time?", "answer": "48 hours", "keywords": "shipping"},
    )
    response = await admin_client.get(f"/api/v1/admin/{test_tenant.slug}/knowledge?q=return")
    data = response.json()
    assert data["total"] == 1


async def test_get_knowledge(admin_client, test_tenant):
    r = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/knowledge",
        json={"question": "Sizing?", "answer": "See size chart"},
    )
    item_id = r.json()["id"]
    response = await admin_client.get(f"/api/v1/admin/{test_tenant.slug}/knowledge/{item_id}")
    assert response.status_code == 200
    assert response.json()["id"] == item_id


async def test_update_knowledge(admin_client, test_tenant):
    r = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/knowledge",
        json={"question": "Old?", "answer": "Old answer"},
    )
    item_id = r.json()["id"]
    response = await admin_client.put(
        f"/api/v1/admin/{test_tenant.slug}/knowledge/{item_id}",
        json={"answer": "New answer", "status": "draft"},
    )
    data = response.json()
    assert data["answer"] == "New answer"
    assert data["status"] == "draft"
    assert data["question"] == "Old?"  # unchanged


async def test_delete_knowledge_soft(admin_client, test_tenant):
    r = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/knowledge",
        json={"question": "Delete me?", "answer": "OK"},
    )
    item_id = r.json()["id"]
    resp = await admin_client.delete(f"/api/v1/admin/{test_tenant.slug}/knowledge/{item_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"
    get_resp = await admin_client.get(f"/api/v1/admin/{test_tenant.slug}/knowledge/{item_id}")
    assert get_resp.json()["status"] == "archived"


async def test_knowledge_requires_auth(client, test_tenant):
    response = await client.post(
        f"/api/v1/admin/{test_tenant.slug}/knowledge",
        json={"question": "x?", "answer": "x"},
    )
    assert response.status_code == 401


async def test_knowledge_tenant_isolation(admin_client, test_tenant, db):
    await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/knowledge",
        json={"question": "TenantA?", "answer": "TenantA"},
    )
    from app.schemas.knowledge import KnowledgeListParams
    from app.services.knowledge_service import list_knowledge

    items, total = list_knowledge(db, "other-random-id", KnowledgeListParams())
    assert total == 0


async def test_create_category(admin_client, test_tenant):
    response = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/categories",
        json={"name": "Returns", "description": "Return policies"},
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Returns"
```

- [ ] **Step 3: Run tests**

```bash
D:\conda\Scripts\conda.exe run -n smart-cs pytest tests/test_admin_knowledge_api.py -v
```

Expected: 11 tests pass

---

### Task 6: config.py — Add Embedding Fields

**Files:** Modify `app/config.py`, Modify `.env.example`

- [ ] **Step 1: Add to Settings class**

```python
# Add after existing fields in app/config.py
embedding_provider: str = "openai"
embedding_api_key: str = ""
embedding_model: str = "text-embedding-3-small"
```

- [ ] **Step 2: Add to .env.example**

```
EMBEDDING_PROVIDER=openai
EMBEDDING_API_KEY=
EMBEDDING_MODEL=text-embedding-3-small
```

---

### Task 7: core/embedding/ — Embedding Abstraction Layer

**Files:** Create `app/core/embedding/__init__.py`, `app/core/embedding/base.py`, `app/core/embedding/openai_provider.py`, `app/core/embedding/bge_provider.py`

**Produces:** `BaseEmbeddingProvider` (ABC), `OpenAIEmbeddingProvider`, `BGEBembeddingProvider`, `get_embedding_provider(settings) -> BaseEmbeddingProvider`

- [ ] **Step 1: Write base.py**

```python
"""Embedding provider abstract base class."""

from abc import ABC, abstractmethod


class BaseEmbeddingProvider(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for a batch of texts."""

    @property
    @abstractmethod
    def dim(self) -> int:
        """Return embedding vector dimension."""
```

- [ ] **Step 2: Write openai_provider.py**

```python
"""OpenAI text-embedding-3-small provider."""

from openai import AsyncOpenAI

from app.core.embedding.base import BaseEmbeddingProvider


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(input=texts, model=self._model)
        return [d.embedding for d in response.data]

    @property
    def dim(self) -> int:
        return 1536
```

- [ ] **Step 3: Write bge_provider.py**

```python
"""BGE local embedding provider via sentence-transformers."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from app.core.embedding.base import BaseEmbeddingProvider

_executor = ThreadPoolExecutor(max_workers=1)


class BGEBembeddingProvider(BaseEmbeddingProvider):
    def __init__(self, model_name: str = "BAAI/bge-large-zh-v1.5"):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_name)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        loop = asyncio.get_running_loop()
        embeddings = await loop.run_in_executor(
            _executor, self._model.encode, texts, True
        )
        return [e.tolist() for e in embeddings]

    @property
    def dim(self) -> int:
        return 1024
```

- [ ] **Step 4: Write __init__.py with factory**

```python
"""Embedding provider factory."""

from app.config import Settings
from app.core.embedding.base import BaseEmbeddingProvider
from app.core.embedding.openai_provider import OpenAIEmbeddingProvider
from app.core.embedding.bge_provider import BGEBembeddingProvider


def get_embedding_provider(settings: Settings) -> BaseEmbeddingProvider:
    if settings.embedding_provider == "bge":
        return BGEBembeddingProvider(model_name=settings.embedding_model)
    return OpenAIEmbeddingProvider(
        api_key=settings.embedding_api_key or settings.llm_api_key,
        model=settings.embedding_model,
    )
```

- [ ] **Step 5: Verify imports**

```bash
D:/conda/Scripts/conda.exe run -n smart-cs python -c "import sys; sys.path.insert(0,'D:/AAA/smart-cs'); from app.core.embedding import get_embedding_provider; print('OK')"
```

Expected: "OK"

### Task 8: core/retrieval/vector_store.py — ChromaDB

**Files:** Modify `app/core/retrieval/vector_store.py`

- [ ] **Step 1: Write vector_store.py**

```python
"""ChromaDB vector store with per-tenant collection isolation."""

import chromadb
from chromadb.config import Settings as ChromaSettings


class VectorStore:
    def __init__(self, persist_dir: str):
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    def _coll_name(self, tenant_slug: str) -> str:
        return f"{tenant_slug}_knowledge"

    def get_collection(self, tenant_slug: str):
        return self._client.get_or_create_collection(
            name=self._coll_name(tenant_slug),
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, tenant_slug: str, doc_id: str, embedding: list[float], metadata: dict) -> None:
        coll = self.get_collection(tenant_slug)
        coll.add(ids=[doc_id], embeddings=[embedding], metadatas=[metadata])

    def update(self, tenant_slug: str, doc_id: str, embedding: list[float], metadata: dict) -> None:
        coll = self.get_collection(tenant_slug)
        coll.update(ids=[doc_id], embeddings=[embedding], metadatas=[metadata])

    def delete(self, tenant_slug: str, doc_id: str) -> None:
        coll = self.get_collection(tenant_slug)
        try:
            coll.delete(ids=[doc_id])
        except Exception:
            pass

    def search(
        self, tenant_slug: str, query_embedding: list[float], top_k: int = 5
    ) -> list[tuple[str, float]]:
        coll = self.get_collection(tenant_slug)
        if coll.count() == 0:
            return []
        n = min(top_k, coll.count())
        results = coll.query(query_embeddings=[query_embedding], n_results=n)
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        return list(zip(ids, distances))
```

- [ ] **Step 2: Verify import**

```bash
D:/conda/Scripts/conda.exe run -n smart-cs python -c "import sys; sys.path.insert(0,'D:/AAA/smart-cs'); from app.core.retrieval.vector_store import VectorStore; print('OK')"
```

Expected: "OK"

### Task 9: core/retrieval/bm25_index.py — BM25

**Files:** Modify `app/core/retrieval/bm25_index.py`

- [ ] **Step 1: Write bm25_index.py**

```python
"""BM25 keyword index with per-tenant in-memory instances."""

import jieba
from rank_bm25 import BM25Okapi


def _tokenize(text: str) -> list[str]:
    tokens = [t.strip().lower() for t in jieba.lcut(text) if t.strip()]
    return [t for t in tokens if len(t) > 1 or t.isalnum()]


class BM25IndexManager:
    def __init__(self):
        self._indexes: dict[str, BM25Okapi] = {}
        self._doc_ids: dict[str, list[str]] = {}

    def _rebuild(self, tenant_slug: str, corpus: list[tuple[str, str]]) -> None:
        if not corpus:
            self._indexes.pop(tenant_slug, None)
            self._doc_ids.pop(tenant_slug, None)
            return
        self._doc_ids[tenant_slug] = [doc_id for doc_id, _ in corpus]
        tokenized = [_tokenize(text) for _, text in corpus]
        self._indexes[tenant_slug] = BM25Okapi(tokenized)

    def build(self, tenant_slug: str, corpus: list[tuple[str, str]]) -> None:
        self._rebuild(tenant_slug, corpus)

    def has_index(self, tenant_slug: str) -> bool:
        return tenant_slug in self._indexes

    def search(
        self, tenant_slug: str, query: str, top_k: int = 5
    ) -> list[tuple[str, float]]:
        if not self.has_index(tenant_slug):
            return []
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []
        scores = self._indexes[tenant_slug].get_scores(query_tokens)
        doc_ids = self._doc_ids[tenant_slug]
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [
            (doc_ids[idx], score) for idx, score in ranked[:top_k] if score > 0
        ]

    def add(self, tenant_slug: str, doc_id: str, text: str) -> None:
        if self.has_index(tenant_slug):
            current = [(did, "") for did in self._doc_ids.get(tenant_slug, [])]
            current.append((doc_id, text))
            self._rebuild(tenant_slug, current)
        else:
            self._rebuild(tenant_slug, [(doc_id, text)])

    def remove(self, tenant_slug: str, doc_id: str) -> None:
        if not self.has_index(tenant_slug):
            return
        current = [
            (did, "") for did in self._doc_ids.get(tenant_slug, []) if did != doc_id
        ]
        self._rebuild(tenant_slug, current)
```

- [ ] **Step 2: Verify import**

```bash
D:/conda/Scripts/conda.exe run -n smart-cs python -c "import sys; sys.path.insert(0,'D:/AAA/smart-cs'); from app.core.retrieval.bm25_index import BM25IndexManager; print('OK')"
```

Expected: "OK"

### Task 10: core/retrieval/fusion.py — RRF

**Files:** Modify `app/core/retrieval/fusion.py`

- [ ] **Step 1: Write fusion.py**

```python
"""RRF (Reciprocal Rank Fusion) merges vector and BM25 results."""


def rrf_fusion(
    vector_results: list[tuple[str, float]],
    bm25_results: list[tuple[str, float]],
    k: int = 60,
    top_k: int = 5,
) -> list[dict]:
    scores: dict[str, tuple[float, set[str]]] = {}

    for rank, (doc_id, _) in enumerate(vector_results, start=1):
        entry = scores.setdefault(doc_id, (0.0, set()))
        scores[doc_id] = (entry[0] + 1.0 / (k + rank), entry[1] | {"vector"})

    for rank, (doc_id, _) in enumerate(bm25_results, start=1):
        entry = scores.setdefault(doc_id, (0.0, set()))
        scores[doc_id] = (entry[0] + 1.0 / (k + rank), entry[1] | {"bm25"})

    ranked = sorted(scores.items(), key=lambda x: x[1][0], reverse=True)
    return [
        {"doc_id": doc_id, "score": round(score, 4), "sources": sorted(sources)}
        for doc_id, (score, sources) in ranked[:top_k]
    ]
```

- [ ] **Step 2: Smoke test**

```bash
D:/conda/Scripts/conda.exe run -n smart-cs python -c "from app.core.retrieval.fusion import rrf_fusion; r = rrf_fusion([('a',0.9)],[('b',5.0)]); assert r[0]['doc_id'] == 'a'; print('OK')"
```

Expected: "OK"

### Task 11: services/knowledge_service.py — Add dual-write hooks

**Files:** Modify `app/services/knowledge_service.py`

Add after existing imports:
```python
def _get_stores():
    from app.core.retrieval_module import get_vector_store, get_bm25_manager, get_embedding_provider
    return get_vector_store(), get_bm25_manager(), get_embedding_provider()
```

Add `_sync_add` and `_sync_remove` helpers. Update `create_knowledge`, `update_knowledge`, `delete_knowledge` signatures to accept optional `tenant_slug: str = ""` parameter.

Logic: when `tenant_slug` is provided, after SQL transaction commits, sync to ChromaDB + BM25. On sync failure, rollback SQL.

API endpoints in `admin/knowledge.py` pass `tenant_slug=tenant_slug` to all service calls.

### Task 12: app/core/retrieval_module.py + main.py lifespan update

**Files:** Create `app/core/retrieval_module.py`, Modify `app/main.py`

Create `app/core/retrieval_module.py`:
```python
"""Singleton accessors for retrieval services, set during lifespan."""

_vector_store = None
_bm25_manager = None
_embedding_provider = None


def get_vector_store():
    assert _vector_store is not None, "VectorStore not initialized"
    return _vector_store


def get_bm25_manager():
    assert _bm25_manager is not None, "BM25IndexManager not initialized"
    return _bm25_manager


def get_embedding_provider():
    assert _embedding_provider is not None, "EmbeddingProvider not initialized"
    return _embedding_provider
```

Update `main.py` lifespan to init all three singletons and build BM25 for existing tenants.

### Task 13: tests/test_retrieval.py + test_tenant_isolation.py

**Files:** Modify both files with actual tests (not stubs).

test_retrieval.py: `test_bm25_build_and_search`, `test_rrf_fusion`, `test_vector_store_crud`, `test_tenant_isolation_vector_store`
test_tenant_isolation.py: `test_knowledge_not_visible_across_tenants`

### Task 14: Final Integration Verification

- [ ] **Run full test suite + curl**

```bash
D:/conda/Scripts/conda.exe run -n smart-cs pytest tests/ -v
```

Expected: 15+ tests pass

```bash
cd D:/AAA/smart-cs && rm -f ./smartcs.db
D:/conda/Scripts/conda.exe run -n smart-cs uvicorn app.main:app --host 127.0.0.1 --port 8000 &
sleep 3
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/api/v1/admin/demo/knowledge
# Expected: health 200, admin without auth 401
```
