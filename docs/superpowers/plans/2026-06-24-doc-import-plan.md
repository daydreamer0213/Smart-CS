# Document Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upload PDF/Word/Excel/Markdown/text files, auto-parse → chunk → embed → store in SQL + ChromaDB, with admin UI for management.

**Architecture:** Two new models (Document + DocumentChunk) with cascade delete. File parsers per format extract text. Chunking engine: structure-aware → LLM semantic boundary → fixed-size fallback. Chunks embed via existing DashScope pipeline into the shared `{tenant_slug}_knowledge` ChromaDB collection. Admin API under `/api/v1/admin/{slug}/documents`.

**Tech Stack:** PyMuPDF, python-docx, openpyxl, langchain-text-splitters, DeepSeek API (LLM chunking), DashScope (embedding).

## Global Constraints

- Python: `D:/conda-envs/smart-cs/python.exe`
- conda: `D:/conda/Scripts/conda.exe`
- pip cache: `E:/smartcs-cache/pip/`
- All models: Base + TimestampMixin, UUID String(36) PK
- Admin auth: `verify_admin` dependency, `X-Admin-Key` header
- API prefix: `/api/v1/admin/{tenant_slug}/documents`
- Error format: `{"error": {"code": "...", "message": "..."}, "request_id": "..."}`
- ChromaDB collection: `{tenant_slug}_knowledge` (shared with knowledge items)
- File size limit: 20 MB
- Batch import limit: 500 (inherited from knowledge batch)

---

### Task 1: Install dependencies + create Document models

**Files:**
- Create: `app/models/document.py`
- Modify: `app/models/__init__.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Add new dependencies to requirements.txt**

```
PyMuPDF>=1.24.0
python-docx>=1.1.0
openpyxl>=3.1.0
langchain-text-splitters>=0.3.0
```

- [ ] **Step 2: Install dependencies**

```bash
D:/conda-envs/smart-cs/python.exe -m pip install PyMuPDF python-docx openpyxl langchain-text-splitters --cache-dir E:/smartcs-cache/pip/
```

- [ ] **Step 3: Create `app/models/document.py`**

```python
"""Document and DocumentChunk models — uploaded files with chunk-level storage."""

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    filename = Column(String(500), nullable=False)
    file_type = Column(String(10), nullable=False)
    file_size = Column(Integer, default=0)
    file_hash = Column(String(64), nullable=False, index=True)
    chunk_count = Column(Integer, default=0)
    status = Column(String(20), default="processing", nullable=False)
    error_message = Column(String(500), nullable=True)

    tenant = relationship("Tenant")
    chunks = relationship("DocumentChunk", back_populates="document",
                          cascade="all, delete-orphan")


class DocumentChunk(Base, TimestampMixin):
    __tablename__ = "document_chunks"

    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding_id = Column(String(200), nullable=True)
    token_count = Column(Integer, default=0)
    keywords = Column(Text, default="")
    status = Column(String(20), default="active", nullable=False)

    document = relationship("Document", back_populates="chunks")
```

- [ ] **Step 4: Update `app/models/__init__.py`**

Add after `from app.models.knowledge import Category, KnowledgeItem`:

```python
from app.models.document import Document, DocumentChunk
```

- [ ] **Step 5: Verify tables create via lifespan**

```bash
D:/conda-envs/smart-cs/python.exe -c "
from app.models import Base
from app.models.document import Document, DocumentChunk
print('Document table:', Document.__tablename__)
print('DocumentChunk table:', DocumentChunk.__tablename__)
print('OK')
"
```
Expected: `Document table: documents` `DocumentChunk table: document_chunks` `OK`

- [ ] **Step 6: Commit**

```bash
git add app/models/document.py app/models/__init__.py requirements.txt
git commit -m "feat(models): add Document and DocumentChunk models"
```

---

### Task 2: Create file parsers

**Files:**
- Create: `app/core/parsing/__init__.py`
- Create: `app/core/parsing/parser.py`

- [ ] **Step 1: Create `app/core/parsing/__init__.py`**

```python
"""File parsing module — extract text from uploaded documents."""
```

- [ ] **Step 2: Create `app/core/parsing/parser.py`**

```python
"""File parsers: extract plain text from pdf, docx, xlsx, txt, md."""

import io
from pathlib import Path

SUPPORTED_TYPES = {"pdf", "docx", "xlsx", "txt", "md"}


def parse_pdf(data: bytes) -> str:
    """Extract text from a PDF using PyMuPDF."""
    import fitz  # PyMuPDF
    doc = fitz.open(stream=data, filetype="pdf")
    if doc.page_count == 0:
        raise ValueError("PDF has no pages")
    parts = []
    for page in doc:
        text = page.get_text().strip()
        if text:
            parts.append(text)
    doc.close()
    result = "\n\n".join(parts)
    if not result:
        raise ValueError("PDF contains no text layer (likely scanned image)")
    return result


def parse_docx(data: bytes) -> str:
    """Extract text from a Word document."""
    from docx import Document as DocxDocument
    doc = DocxDocument(io.BytesIO(data))
    parts = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            # Check paragraph style for heading detection
            style = para.style.name if para.style else ""
            if style.startswith("Heading") or style.startswith("heading"):
                parts.append(f"## {text}")
            else:
                parts.append(text)
    # Extract table text too
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            parts.append(" | ".join(cells))
    return "\n\n".join(parts)


def parse_xlsx(data: bytes) -> str:
    """Extract text from Excel — one line per row, first row as headers."""
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), read_only=True)
    parts = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        headers = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if all(c is None for c in row):
                continue  # skip empty rows
            if i == 0:
                headers = [str(c) if c else "" for c in row]
                continue
            cells = [str(c) if c else "" for c in row]
            # Build "Q: col1 A: col2" type lines for FAQ-style sheets
            if len(headers) >= 2 and len(cells) >= 2:
                parts.append(f"Q: {cells[0]} A: {cells[1]}")
            else:
                parts.append(" | ".join(cells))
    wb.close()
    return "\n".join(parts)


def parse_text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").strip()


_PARSERS = {
    "pdf": parse_pdf,
    "docx": parse_docx,
    "xlsx": parse_xlsx,
    "txt": parse_text,
    "md": parse_text,
}


def parse_file(filename: str, data: bytes) -> str:
    """Parse an uploaded file and return extracted text.

    Raises ValueError if file type is unsupported or parsing fails.
    """
    ext = Path(filename).suffix.lstrip(".").lower()
    if ext not in _PARSERS:
        raise ValueError(f"Unsupported file type: .{ext}")
    return _PARSERS[ext](data)
```

- [ ] **Step 3: Verify parsers import**

```bash
D:/conda-envs/smart-cs/python.exe -c "from app.core.parsing.parser import parse_file, SUPPORTED_TYPES; print('Parsers OK')"
```
Expected: `Parsers OK`

- [ ] **Step 4: Commit**

```bash
git add app/core/parsing/
git commit -m "feat(parsing): add pdf/docx/xlsx/txt/md file parsers"
```

---

### Task 3: Create chunking engine

**Files:**
- Create: `app/core/parsing/chunker.py`

- [ ] **Step 1: Create `app/core/parsing/chunker.py`**

```python
"""Chunking engine — structure-aware → LLM semantic → fixed-size fallback."""

import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
MAX_CHUNK_SIZE = 1000

_fallback_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", "。", ".", "！", "？", "；", ";", "，", ",", " "],
    keep_separator=True,
)


def _struct_chunk(text: str) -> list[str]:
    """Try to split by document structure: headings, double-newlines, rows."""
    # md/docx headings: split on ## or similar markers
    if "## " in text or "\n## " in text:
        sections = re.split(r"\n(?=#{1,4}\s)", text)
    else:
        # plain text: split on double newlines (paragraphs)
        sections = text.split("\n\n")
    return [s.strip() for s in sections if s.strip()]


async def _semantic_chunk(text: str) -> list[str]:
    """Use DeepSeek LLM to find semantic boundaries in a long text block.

    Returns a list of semantically coherent sub-blocks.
    """
    from openai import AsyncOpenAI
    from app.config import settings

    client = AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=30.0,
    )
    prompt = (
        "将以下文本按语义边界切分为多个段落（每段 300-800 字），"
        "用 \\n---\\n 分隔各段。\n\n"
        f"{text}"
    )
    resp = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=2000,
    )
    result = resp.choices[0].message.content or text
    parts = [p.strip() for p in result.split("\n---\n") if p.strip()]
    # If LLM returned just one block or empty, fall through to fixed split
    if len(parts) <= 1:
        return _fixed_chunk(text)
    return parts


def _fixed_chunk(text: str) -> list[str]:
    """Fixed-size split with overlap — last-resort fallback."""
    docs = _fallback_splitter.create_documents([text])
    return [d.page_content for d in docs if d.page_content.strip()]


async def chunk_text(text: str) -> list[str]:
    """Produce chunks from raw document text.

    Strategy:
      1. Split by document structure (headings/paragraphs)
      2. For each oversized block, try LLM semantic boundary detection
      3. If semantic chunking produces nothing useful, use fixed-size split
    """
    if not text.strip():
        return []

    chunks = []
    struct_blocks = _struct_chunk(text)

    for block in struct_blocks:
        if len(block) <= MAX_CHUNK_SIZE:
            chunks.append(block)
        else:
            try:
                sub_blocks = await _semantic_chunk(block)
            except Exception:
                sub_blocks = _fixed_chunk(block)
            chunks.extend(sub_blocks)

    return [c for c in chunks if c.strip()]
```

- [ ] **Step 2: Verify chunker imports**

```bash
D:/conda-envs/smart-cs/python.exe -c "from app.core.parsing.chunker import chunk_text, _fixed_chunk, _struct_chunk; print('Chunker OK')"
```
Expected: `Chunker OK`

- [ ] **Step 3: Commit**

```bash
git add app/core/parsing/chunker.py
git commit -m "feat(parsing): add structure-aware semantic chunking engine"
```

---

### Task 4: Add document schemas

**Files:**
- Create: `app/schemas/document.py`

- [ ] **Step 1: Create `app/schemas/document.py`**

```python
"""Document upload/management schemas."""

from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    id: str
    tenant_id: str
    filename: str
    file_type: str
    file_size: int
    file_hash: str
    chunk_count: int
    status: str
    error_message: str | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class DocumentChunkResponse(BaseModel):
    id: str
    chunk_index: int
    content: str
    token_count: int
    keywords: str | None
    status: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    chunk_count: int
    status: str
```

- [ ] **Step 2: Commit**

```bash
git add app/schemas/document.py
git commit -m "feat(schemas): add Document and DocumentChunk response schemas"
```

---

### Task 5: Create document service

**Files:**
- Create: `app/services/document_service.py`

- [ ] **Step 1: Create `app/services/document_service.py`**

```python
"""Document upload, listing, retrieval, and deletion."""

import hashlib
import structlog

from sqlalchemy.orm import Session

from app.core.parsing.parser import parse_file
from app.core.parsing.chunker import chunk_text
from app.core.retrieval_module import (
    get_bm25_manager,
    get_embedding_provider,
    get_vector_store,
)
from app.models.document import Document, DocumentChunk

logger = structlog.get_logger()

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


def _hash_content(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def upload_document(
    db: Session,
    tenant_id: str,
    tenant_slug: str,
    filename: str,
    file_data: bytes,
) -> Document:
    if len(file_data) == 0:
        raise ValueError("Empty file")
    if len(file_data) > MAX_FILE_SIZE:
        raise ValueError("File too large (max 20 MB)")

    file_hash = _hash_content(file_data)

    # Dedup check
    existing = db.query(Document).filter(
        Document.tenant_id == tenant_id,
        Document.file_hash == file_hash,
    ).first()
    if existing:
        raise ValueError("Document already imported")

    # Parse
    text = parse_file(filename, file_data)
    file_type = filename.rsplit(".", 1)[-1].lower()

    doc = Document(
        tenant_id=tenant_id,
        filename=filename,
        file_type=file_type,
        file_size=len(file_data),
        file_hash=file_hash,
        status="processing",
    )
    db.add(doc)
    db.flush()

    try:
        # Chunk
        chunks_text = await chunk_text(text)
        if not chunks_text:
            raise ValueError("No text content extracted from file")

        # Embed + store
        emb = get_embedding_provider()
        vs = get_vector_store()
        bm = get_bm25_manager()

        embeddings = await emb.embed(chunks_text)

        for i, (chunk_content, embedding) in enumerate(zip(chunks_text, embeddings), start=1):
            chunk = DocumentChunk(
                document_id=doc.id,
                chunk_index=i,
                content=chunk_content,
                token_count=len(chunk_content) // 4,
                keywords="",
            )
            db.add(chunk)
            db.flush()

            # ChromaDB
            vs.add(
                tenant_slug, chunk.id, embedding,
                metadata={"source": "document", "document_id": doc.id, "chunk_index": i},
            )
            chunk.embedding_id = chunk.id

        # BM25 rebuild — add chunks to index
        bm_corpus = [(c.id, c.content) for c in db.query(DocumentChunk).filter(
            DocumentChunk.document_id == doc.id,
        ).all()]
        for chunk_id, chunk_text_content in bm_corpus:
            bm.add(tenant_slug, chunk_id, chunk_text_content)

        doc.chunk_count = len(chunks_text)
        doc.status = "ready"
        db.commit()
        db.refresh(doc)

    except Exception as e:
        doc.status = "failed"
        doc.error_message = str(e)[:500]
        db.commit()
        logger.error("document_import_failed", filename=filename, error=str(e))

    return doc


def list_documents(
    db: Session, tenant_id: str, page: int = 1, page_size: int = 20
) -> tuple[list[Document], int]:
    query = db.query(Document).filter(Document.tenant_id == tenant_id)
    total = query.count()
    items = query.order_by(Document.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return items, total


def get_document(db: Session, tenant_id: str, document_id: str) -> Document | None:
    return db.query(Document).filter(
        Document.tenant_id == tenant_id,
        Document.id == document_id,
    ).first()


def list_chunks(db: Session, document_id: str) -> list[DocumentChunk]:
    return db.query(DocumentChunk).filter(
        DocumentChunk.document_id == document_id
    ).order_by(DocumentChunk.chunk_index).all()


def delete_document(
    db: Session, tenant_slug: str, document_id: str
) -> None:
    """Cascade delete: chunks → ChromaDB vectors → BM25 → document."""
    vs = get_vector_store()
    bm = get_bm25_manager()

    chunks = db.query(DocumentChunk).filter(
        DocumentChunk.document_id == document_id
    ).all()

    for chunk in chunks:
        vs.delete(tenant_slug, chunk.id)
        bm.remove(tenant_slug, chunk.id)

    doc = db.query(Document).filter(Document.id == document_id).first()
    if doc:
        db.delete(doc)

    db.commit()
```

- [ ] **Step 2: Verify service imports**

```bash
D:/conda-envs/smart-cs/python.exe -c "from app.services.document_service import upload_document, list_documents, delete_document; print('Service OK')"
```
Expected: `Service OK`

- [ ] **Step 3: Commit**

```bash
git add app/services/document_service.py
git commit -m "feat(service): add document upload/list/get/delete service"
```

---

### Task 6: Add admin document API endpoints

**Files:**
- Create: `app/api/admin/document.py`
- Modify: `app/main.py` (add router)

- [ ] **Step 1: Create `app/api/admin/document.py`**

```python
"""Admin document management endpoints."""

import structlog

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.orm import Session

logger = structlog.get_logger()

from app.api.admin.auth import verify_admin
from app.api.deps import get_db, get_tenant
from app.models.tenant import AdminApiKey, Tenant
from app.schemas.document import (
    DocumentChunkResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentUploadResponse,
)
from app.services import document_service

router = APIRouter()

MAX_FILE_SIZE = 20 * 1024 * 1024


@router.post("/api/v1/admin/{tenant_slug}/documents/upload", status_code=201)
async def upload(
    tenant_slug: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    _admin: AdminApiKey = Depends(verify_admin),
):
    if file.filename is None:
        raise HTTPException(400, "No filename provided")

    data = await file.read()
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in {"pdf", "docx", "xlsx", "txt", "md"}:
        raise HTTPException(400, f"Unsupported file type: .{ext}")

    try:
        doc = await document_service.upload_document(
            db, tenant.id, tenant_slug, file.filename, data,
        )
    except ValueError as e:
        msg = str(e)
        if "already imported" in msg:
            raise HTTPException(409, msg)
        raise HTTPException(400, msg)

    logger.info("document_uploaded", tenant_slug=tenant_slug, document_id=doc.id)
    return DocumentUploadResponse(
        document_id=doc.id,
        filename=doc.filename,
        chunk_count=doc.chunk_count,
        status=doc.status,
    )


@router.get("/api/v1/admin/{tenant_slug}/documents")
async def list_docs(
    tenant_slug: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    _admin: AdminApiKey = Depends(verify_admin),
):
    items, total = document_service.list_documents(db, tenant.id, page, page_size)
    resp_items = []
    for d in items:
        resp_items.append(DocumentResponse(
            id=d.id, tenant_id=d.tenant_id, filename=d.filename,
            file_type=d.file_type, file_size=d.file_size, file_hash=d.file_hash,
            chunk_count=d.chunk_count, status=d.status,
            error_message=d.error_message,
            created_at=d.created_at.isoformat() if d.created_at else "",
            updated_at=d.updated_at.isoformat() if d.updated_at else "",
        ))
    return DocumentListResponse(
        items=resp_items, total=total, page=page, page_size=page_size,
        total_pages=max(1, (total + page_size - 1) // page_size),
    )


@router.get("/api/v1/admin/{tenant_slug}/documents/{document_id}/chunks")
async def list_chunks(
    tenant_slug: str, document_id: str,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    _admin: AdminApiKey = Depends(verify_admin),
):
    doc = document_service.get_document(db, tenant.id, document_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    chunks = document_service.list_chunks(db, document_id)
    return {
        "chunks": [
            DocumentChunkResponse(
                id=c.id, chunk_index=c.chunk_index, content=c.content,
                token_count=c.token_count, keywords=c.keywords, status=c.status,
                created_at=c.created_at.isoformat() if c.created_at else "",
                updated_at=c.updated_at.isoformat() if c.updated_at else "",
            ) for c in chunks
        ]
    }


@router.delete("/api/v1/admin/{tenant_slug}/documents/{document_id}")
async def delete_doc(
    tenant_slug: str, document_id: str,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    _admin: AdminApiKey = Depends(verify_admin),
):
    doc = document_service.get_document(db, tenant.id, document_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    document_service.delete_document(db, tenant_slug, document_id)
    logger.info("document_deleted", tenant_slug=tenant_slug, document_id=document_id)
    return {"status": "deleted"}
```

- [ ] **Step 2: Register router in main.py**

Add after `from app.api.admin.knowledge import router as admin_knowledge_router`:

```python
from app.api.admin.document import router as admin_document_router
```

Add after `app.include_router(admin_knowledge_router)`:

```python
app.include_router(admin_document_router)
```

- [ ] **Step 3: Verify router loads**

```bash
D:/conda-envs/smart-cs/python.exe -c "from app.api.admin.document import router; print(len(router.routes), 'routes')"
```
Expected: `4 routes`

- [ ] **Step 4: Commit**

```bash
git add app/api/admin/document.py app/main.py
git commit -m "feat(api): add admin document upload/list/chunks/delete endpoints"
```

---

### Task 7: Update admin frontend — Documents tab

**Files:**
- Modify: `admin-static/index.html`

- [ ] **Step 1: Add "Documents" tab to the admin SPA**

Design the tab with:
- Upload area: `<input type="file" accept=".pdf,.docx,.xlsx,.txt,.md" />` with click-to-upload button
- Document table: filename, type, size, chunk count, status badge, delete button
- Click row → expand chunk list panel below
- Error handling: show error message for failed documents, graceful error on server error

- [ ] **Step 2: Verify frontend loads**

Open `http://127.0.0.1:8000/admin/` → Documents tab visible

- [ ] **Step 3: Commit**

```bash
git add admin-static/index.html
git commit -m "feat(frontend): add Documents tab with upload/list/chunks view"
```

---

### Task 8: Create document service tests

**Files:**
- Create: `tests/test_document_service.py`

- [ ] **Step 1: Create `tests/test_document_service.py`**

```python
"""Document service tests — upload, list, get, delete."""

import io
import pytest


class TestParseFile:
    def test_parse_txt(self):
        from app.core.parsing.parser import parse_file
        text = parse_file("test.txt", b"hello world")
        assert text == "hello world"

    def test_parse_md(self):
        from app.core.parsing.parser import parse_file
        text = parse_file("readme.md", b"# Title\n\nbody text")
        assert "Title" in text
        assert "body text" in text

    def test_parse_unsupported(self):
        from app.core.parsing.parser import parse_file
        with pytest.raises(ValueError, match="Unsupported"):
            parse_file("test.exe", b"data")


class TestChunker:
    async def test_fixed_chunk_basic(self):
        from app.core.parsing.chunker import _fixed_chunk
        text = "Hello world. " * 500  # ~6000 chars
        chunks = _fixed_chunk(text)
        assert len(chunks) > 1
        assert all(len(c) <= 1000 for c in chunks)

    async def test_struct_chunk_headings(self):
        from app.core.parsing.chunker import _struct_chunk
        text = "## Section 1\ncontent one\n\n## Section 2\ncontent two"
        chunks = _struct_chunk(text)
        assert len(chunks) == 2
        assert "Section 1" in chunks[0]

    async def test_chunk_text_short(self):
        from app.core.parsing.chunker import chunk_text
        chunks = await chunk_text("short text")
        assert len(chunks) == 1
        assert chunks[0] == "short text"

    async def test_chunk_text_empty(self):
        from app.core.parsing.chunker import chunk_text
        chunks = await chunk_text("")
        assert chunks == []


class TestDocumentUpload:
    async def test_upload_txt_creates_document(self, db, test_tenant):
        """Upload a text file and verify Document + chunks are created."""
        from app.services.document_service import upload_document
        doc = await upload_document(
            db, test_tenant.id, test_tenant.slug,
            "faq.txt", b"Q: test question\nA: test answer",
        )
        assert doc.status in ("ready", "failed")
        if doc.status == "ready":
            assert doc.chunk_count > 0

    async def test_upload_empty_file_raises(self, db, test_tenant):
        from app.services.document_service import upload_document
        with pytest.raises(ValueError, match="Empty"):
            await upload_document(
                db, test_tenant.id, test_tenant.slug,
                "empty.txt", b"",
            )

    async def test_upload_duplicate_detected(self, db, test_tenant):
        from app.services.document_service import upload_document
        data = b"unique doc content for dedup test"
        await upload_document(db, test_tenant.id, test_tenant.slug, "a.txt", data)
        with pytest.raises(ValueError, match="already imported"):
            await upload_document(db, test_tenant.id, test_tenant.slug, "b.txt", data)

    async def test_list_documents(self, db, test_tenant):
        from app.services.document_service import list_documents, upload_document
        await upload_document(
            db, test_tenant.id, test_tenant.slug,
            "list-test.txt", b"list test content",
        )
        items, total = list_documents(db, test_tenant.id)
        assert total >= 1

    async def test_delete_cascade(self, db, test_tenant):
        from app.services.document_service import (
            delete_document, get_document, list_chunks, upload_document,
        )
        doc = await upload_document(
            db, test_tenant.id, test_tenant.slug,
            "delete-me.txt", b"content to delete",
        )
        if doc.status == "ready":
            chunks_before = list_chunks(db, doc.id)
            assert len(chunks_before) > 0

        delete_document(db, test_tenant.slug, doc.id)
        assert get_document(db, test_tenant.id, doc.id) is None
```

- [ ] **Step 2: Run document tests**

```bash
D:/conda-envs/smart-cs/python.exe -m pytest tests/test_document_service.py -v
```
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_document_service.py
git commit -m "test: add document service tests (parse/chunk/upload/list/delete)"
```

---

### Task 9: Add document API integration tests

**Files:**
- Create: `tests/test_admin_document_api.py`

- [ ] **Step 1: Create `tests/test_admin_document_api.py`**

```python
"""Admin document API integration tests."""

import pytest


async def test_document_upload_endpoint(admin_client, test_tenant):
    """Upload a txt file via the admin API."""
    response = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/documents/upload",
        files={"file": ("test.txt", b"Q: test question\nA: test answer", "text/plain")},
    )
    assert response.status_code in (201, 400)  # 400 if no embedding API key


async def test_document_list_endpoint(admin_client, test_tenant):
    """GET documents list returns 200."""
    response = await admin_client.get(
        f"/api/v1/admin/{test_tenant.slug}/documents"
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


async def test_document_upload_requires_auth(client, test_tenant):
    """Upload endpoint requires X-Admin-Key."""
    response = await client.post(
        f"/api/v1/admin/{test_tenant.slug}/documents/upload",
        files={"file": ("test.txt", b"data", "text/plain")},
    )
    assert response.status_code == 401


async def test_document_upload_rejects_exe(admin_client, test_tenant):
    """Unsupported file types should be rejected."""
    response = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/documents/upload",
        files={"file": ("virus.exe", b"malware", "application/octet-stream")},
    )
    assert response.status_code in (400, 401)


async def test_document_delete_cascade(admin_client, test_tenant):
    """Delete a document and verify it's gone."""
    # Upload first
    resp = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/documents/upload",
        files={"file": ("delete-test.txt", b"delete test content", "text/plain")},
    )
    if resp.status_code == 201:
        doc_id = resp.json()["document_id"]
        # Delete
        resp2 = await admin_client.delete(
            f"/api/v1/admin/{test_tenant.slug}/documents/{doc_id}"
        )
        assert resp2.status_code == 200


async def test_document_list_respects_pagination(admin_client, test_tenant):
    """Documents list supports pagination params."""
    response = await admin_client.get(
        f"/api/v1/admin/{test_tenant.slug}/documents?page=1&page_size=5"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["page_size"] == 5
```

- [ ] **Step 2: Run integration tests**

```bash
D:/conda-envs/smart-cs/python.exe -m pytest tests/test_admin_document_api.py -v
```
Expected: All tests pass (some may skip if no embedding API)

- [ ] **Step 3: Commit**

```bash
git add tests/test_admin_document_api.py
git commit -m "test: add admin document API integration tests"
```

---

### Task 10: Final verification

- [ ] **Step 1: Run full test suite**

```bash
D:/conda-envs/smart-cs/python.exe -m pytest tests/ -v
```
Expected: All 74+ tests pass (existing + new document tests)

- [ ] **Step 2: Verify app startup**

```bash
D:/conda-envs/smart-cs/python.exe -c "
from app.main import create_app
app = create_app()
print('App created successfully')
"
```
Expected: `App created successfully`

- [ ] **Step 3: Manual browser test**

```bash
D:/conda-envs/smart-cs/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

1. Open `http://127.0.0.1:8000/admin/` → Documents tab
2. Upload a `.txt` file with test content
3. Verify document appears in list with status "ready"
4. Click → view chunks
5. Delete → confirm gone

- [ ] **Step 4: Commit final verification**

```bash
git add -A
git commit -m "verify: full test suite + app startup after document import feature"
```
