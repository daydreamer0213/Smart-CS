"""Document upload, listing, retrieval, and deletion."""

import asyncio
from datetime import date, datetime, timezone
import hashlib
import time
import structlog

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.core.parsing.quality import (
    SAFE_PARSE_ERROR_MESSAGE,
    evaluate_parse_quality,
    parser_failure_quality,
)
from app.core.parsing.router import parse_structured_file
from app.core.parsing.structured_chunker import CHUNKER_VERSION, chunk_document
from app.core.retrieval_module import (
    get_bm25_manager,
    get_embedding_provider,
    get_vector_store,
)
from app.models.document import Document, DocumentChunk, DocumentFamily
from app.models.user import User
from app.services.document_storage import delete_original, store_original

logger = structlog.get_logger()

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
SAFE_INDEX_ERROR_MESSAGE = "Document indexing failed."
SAFE_EMPTY_ERROR_MESSAGE = "No text content extracted from file."


class DocumentLifecycleError(ValueError):
    """A requested document lifecycle transition is not allowed."""


def _hash_content(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def upload_document(
    db: Session,
    tenant_id: str,
    tenant_slug: str,
    filename: str,
    file_data: bytes,
    audience_roles: list[str] | None = None,
    *,
    family_id: str | None = None,
    family_name: str | None = None,
    effective_date: date | None = None,
    expiry_date: date | None = None,
    owner_user_id: str | None = None,
) -> Document:
    if len(file_data) == 0:
        raise ValueError("Empty file")
    if len(file_data) > MAX_FILE_SIZE:
        raise ValueError("File too large (max 20 MB)")
    if effective_date and expiry_date and expiry_date < effective_date:
        raise ValueError("Expiry date cannot be before effective date")

    file_hash = _hash_content(file_data)
    file_type = filename.rsplit(".", 1)[-1].lower()

    if family_id is None:
        existing = db.query(Document).filter(
            Document.tenant_id == tenant_id,
            Document.file_hash == file_hash,
        ).first()
        if existing:
            raise ValueError("Document already imported")
        family = DocumentFamily(
            tenant_id=tenant_id,
            name=(family_name or "").strip() or filename,
            owner_user_id=owner_user_id,
        )
        version = 1
    else:
        family = db.query(DocumentFamily).filter(
            DocumentFamily.id == family_id,
            DocumentFamily.tenant_id == tenant_id,
        ).first()
        if family is None:
            raise ValueError("Document family not found")
        same_content = db.query(Document).filter(
            Document.tenant_id == tenant_id,
            Document.family_id == family.id,
            Document.file_hash == file_hash,
        ).all()
        if any(
            set(document.audience_roles or []) == set(audience_roles or [])
            and document.effective_date == effective_date
            and document.expiry_date == expiry_date
            for document in same_content
        ):
            raise ValueError("Document already imported")
        version = (
            db.query(func.max(Document.version))
            .filter(Document.family_id == family.id)
            .scalar()
            or 0
        ) + 1

    storage_key = store_original(tenant_id, file_hash, f".{file_type}", file_data)
    if family_id is None:
        db.add(family)
        db.flush()

    doc = Document(
        tenant_id=tenant_id,
        family_id=family.id,
        filename=filename,
        file_type=file_type,
        file_size=len(file_data),
        file_hash=file_hash,
        status="processing",
        audience_roles=audience_roles or [],
        version=version,
        index_generation=1,
        review_status="pending_review",
        effective_date=effective_date,
        expiry_date=expiry_date,
        source_type="upload",
        source_ref=filename,
        storage_key=storage_key,
        owner_user_id=owner_user_id,
        chunker_version=CHUNKER_VERSION,
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model,
    )
    db.add(doc)
    db.flush()
    db.commit()
    db.refresh(doc)
    document_id = doc.id

    parse_started = time.perf_counter()
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

    parsed.quality = evaluate_parse_quality(
        parsed,
        elapsed_ms=max(0.0, (time.perf_counter() - parse_started) * 1000),
        warnings=parsed.quality.warnings,
    )

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

    chunks = []
    for index, parsed_chunk in enumerate(parsed_chunks, start=1):
        chunk = DocumentChunk(
            document_id=doc.id,
            chunk_index=index,
            content=parsed_chunk.content,
            token_count=parsed_chunk.token_count,
            keywords="",
            status="inactive",
            page_start=parsed_chunk.page_start,
            page_end=parsed_chunk.page_end,
            section_path=parsed_chunk.section_path,
            element_types=parsed_chunk.element_types,
            source_element_indexes=parsed_chunk.source_element_indexes,
            index_generation=doc.index_generation,
            chunker_version=CHUNKER_VERSION,
            embedding_model=settings.embedding_model,
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

    db.commit()
    db.refresh(doc)

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
                    "index_generation": doc.index_generation,
                },
            )

        # BM25 rebuild — add chunks to index
        for chunk, _ in chunks:
            bm25_ids.append(chunk.id)
            bm.add(tenant_slug, chunk.id, chunk.content)

        for chunk, _ in chunks:
            chunk.status = "active"
            chunk.embedding_id = chunk.id
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
        db.rollback()
        doc = db.query(Document).filter(Document.id == document_id).one()
        persisted_chunks = db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).all()
        for chunk in persisted_chunks:
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


def review_document(
    db: Session,
    *,
    tenant_id: str,
    document_id: str,
    decision: str,
    reviewer_user_id: str | None,
) -> Document:
    if decision not in {"approved", "rejected"}:
        raise DocumentLifecycleError("Invalid review decision")

    document = get_document(db, tenant_id, document_id)
    if document is None:
        raise DocumentLifecycleError("Document not found")
    if document.family is None:
        raise DocumentLifecycleError("Legacy document has no governance family")
    if document.family.tenant_id != tenant_id:
        raise DocumentLifecycleError("Document not found")
    if document.review_status != "pending_review":
        raise DocumentLifecycleError("Document has already been reviewed")

    if reviewer_user_id:
        reviewer = db.query(User).filter(
            User.id == reviewer_user_id,
            User.tenant_id == tenant_id,
            User.role.in_(("owner", "admin")),
            User.is_active.is_(True),
        ).first()
        if reviewer is None:
            raise DocumentLifecycleError("Reviewer is not authorized")

    if decision == "approved":
        today = date.today()
        if document.status != "ready":
            raise DocumentLifecycleError("Document must be ready before approval")
        if document.parse_quality_status != "passed":
            raise DocumentLifecycleError("Document parse quality must be passed")
        if document.effective_date and document.effective_date > today:
            raise DocumentLifecycleError("Document effective date is in the future")
        if document.expiry_date and document.expiry_date < today:
            raise DocumentLifecycleError("Document is expired")
        document.family.current_document_id = document.id

    document.review_status = decision
    document.reviewed_by_user_id = reviewer_user_id
    document.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(document)
    return document


def delete_document(
    db: Session, tenant_id: str, tenant_slug: str, document_id: str
) -> None:
    """Cascade delete: chunks → ChromaDB vectors → BM25 → document."""
    doc = db.query(Document).filter(
        Document.id == document_id,
        Document.tenant_id == tenant_id,
    ).first()
    if doc is None:
        return
    if doc.family and doc.family.current_document_id == doc.id:
        raise DocumentLifecycleError("Cannot delete the current published document")

    vs = get_vector_store()
    bm = get_bm25_manager()

    chunks = db.query(DocumentChunk).filter(
        DocumentChunk.document_id == document_id
    ).all()

    for chunk in chunks:
        try:
            vs.delete(tenant_slug, chunk.id)
        except Exception as error:
            logger.error(
                "document_vector_cleanup_failed",
                document_id=document_id,
                chunk_id=chunk.id,
                error=str(error),
            )
        try:
            bm.remove(tenant_slug, chunk.id)
        except Exception as error:
            logger.error(
                "document_bm25_cleanup_failed",
                document_id=document_id,
                chunk_id=chunk.id,
                error=str(error),
            )

    storage_key = doc.storage_key
    db.delete(doc)
    db.commit()
    storage_references = (
        db.query(Document).filter(Document.storage_key == storage_key).count()
        if storage_key
        else 0
    )
    if storage_key and storage_references == 0:
        try:
            delete_original(storage_key)
        except (OSError, ValueError) as error:
            logger.error(
                "document_original_cleanup_failed",
                document_id=document_id,
                error=str(error),
            )
