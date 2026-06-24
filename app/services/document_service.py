"""Document upload, listing, retrieval, and deletion."""

import asyncio
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

        # Embed with per-chunk retry (3 attempts each)
        embeddings = []
        emb_retries = 3
        for chunk_text_content in chunks_text:
            for attempt in range(emb_retries):
                try:
                    vec = (await emb.embed([chunk_text_content]))[0]
                    embeddings.append(vec)
                    break
                except Exception:
                    if attempt == emb_retries - 1:
                        raise
                    await asyncio.sleep(2 ** attempt)

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
