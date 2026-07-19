"""Document upload, listing, retrieval, and deletion."""

import asyncio
import hashlib
import structlog

from sqlalchemy.orm import Session

from app.core.parsing.quality import SAFE_PARSE_ERROR_MESSAGE, parser_failure_quality
from app.core.parsing.router import parse_structured_file
from app.core.parsing.structured_chunker import chunk_document
from app.core.retrieval_module import (
    get_bm25_manager,
    get_embedding_provider,
    get_vector_store,
)
from app.models.document import Document, DocumentChunk

logger = structlog.get_logger()

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
SAFE_INDEX_ERROR_MESSAGE = "Document indexing failed."
SAFE_EMPTY_ERROR_MESSAGE = "No text content extracted from file."


def _hash_content(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def upload_document(
    db: Session,
    tenant_id: str,
    tenant_slug: str,
    filename: str,
    file_data: bytes,
    audience_roles: list[str] | None = None,
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

    file_type = filename.rsplit(".", 1)[-1].lower()

    doc = Document(
        tenant_id=tenant_id,
        filename=filename,
        file_type=file_type,
        file_size=len(file_data),
        file_hash=file_hash,
        status="processing",
        audience_roles=audience_roles or [],
    )
    db.add(doc)
    db.flush()

    try:
        parsed = parse_structured_file(filename, file_data)
    except Exception as error:
        quality, safe_message = parser_failure_quality(error)
        doc.parse_quality_status = quality.status
        doc.parse_quality_details = quality.model_dump(exclude={"status"})
        doc.status = "failed"
        doc.error_message = safe_message
        db.commit()
        db.refresh(doc)
        logger.error("document_parse_failed", filename=filename, error=str(error))
        return doc

    doc.parser_name = parsed.parser_name
    doc.parser_version = parsed.parser_version
    doc.page_count = parsed.page_count
    doc.parse_quality_status = parsed.quality.status
    doc.parse_quality_details = parsed.quality.model_dump(exclude={"status"})

    if parsed.quality.status == "failed":
        doc.status = "failed"
        doc.error_message = SAFE_PARSE_ERROR_MESSAGE
        db.commit()
        db.refresh(doc)
        return doc

    try:
        parsed_chunks = chunk_document(parsed, filename)
    except Exception as error:
        doc.status = "failed"
        doc.error_message = SAFE_PARSE_ERROR_MESSAGE
        db.commit()
        db.refresh(doc)
        logger.error("document_chunk_failed", filename=filename, error=str(error))
        return doc

    if not parsed_chunks:
        doc.status = "failed"
        doc.error_message = SAFE_EMPTY_ERROR_MESSAGE
        db.commit()
        db.refresh(doc)
        return doc

    chunk_status = "active" if parsed.quality.status == "passed" else "inactive"
    chunks = []
    for index, parsed_chunk in enumerate(parsed_chunks, start=1):
        chunk = DocumentChunk(
            document_id=doc.id,
            chunk_index=index,
            content=parsed_chunk.content,
            token_count=parsed_chunk.token_count,
            keywords="",
            status=chunk_status,
            page_start=parsed_chunk.page_start,
            page_end=parsed_chunk.page_end,
            section_path=parsed_chunk.section_path,
            element_types=parsed_chunk.element_types,
            source_element_indexes=parsed_chunk.source_element_indexes,
        )
        db.add(chunk)
        db.flush()
        chunks.append((chunk, parsed_chunk))
    doc.chunk_count = len(chunks)

    if parsed.quality.status == "review_required":
        doc.status = "review_required"
        db.commit()
        db.refresh(doc)
        return doc

    vector_ids: list[str] = []
    bm25_ids: list[str] = []
    vs = None
    bm = None
    try:
        emb = get_embedding_provider()
        vs = get_vector_store()
        bm = get_bm25_manager()

        embeddings = []
        for _, parsed_chunk in chunks:
            for attempt in range(3):
                try:
                    embeddings.append(
                        (await emb.embed([parsed_chunk.contextualized_content]))[0]
                    )
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2 ** attempt)

        for (chunk, _), embedding in zip(chunks, embeddings):
            vector_ids.append(chunk.id)
            vs.add(
                tenant_slug,
                chunk.id,
                embedding,
                metadata={
                    "source": "document",
                    "document_id": doc.id,
                    "chunk_index": chunk.chunk_index,
                },
            )
            chunk.embedding_id = chunk.id

        # BM25 rebuild — add chunks to index
        for chunk, _ in chunks:
            bm25_ids.append(chunk.id)
            bm.add(tenant_slug, chunk.id, chunk.content)

        doc.status = "ready"
        db.commit()
        db.refresh(doc)

    except Exception as error:
        if vs is not None:
            for chunk_id in vector_ids:
                try:
                    vs.delete(tenant_slug, chunk_id)
                except Exception:
                    logger.error("document_vector_cleanup_failed", chunk_id=chunk_id)
        if bm is not None:
            for chunk_id in bm25_ids:
                try:
                    bm.remove(tenant_slug, chunk_id)
                except Exception:
                    logger.error("document_bm25_cleanup_failed", chunk_id=chunk_id)
        for chunk, _ in chunks:
            chunk.embedding_id = None
            chunk.status = "inactive"
        doc.status = "failed"
        doc.error_message = SAFE_INDEX_ERROR_MESSAGE
        db.commit()
        db.refresh(doc)
        logger.error("document_index_failed", filename=filename, error=str(error))

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
