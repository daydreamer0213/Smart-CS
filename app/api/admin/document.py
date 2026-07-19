"""Admin document management endpoints."""

from datetime import date
import structlog

from math import isfinite
from typing import get_args, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

logger = structlog.get_logger()

from app.api.admin.auth import admin_auth
from app.api.deps import get_db, get_tenant
from app.core.parsing.contracts import ParseWarning
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.document import (
    DocumentChunkResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentReviewRequest,
    DocumentReviewResponse,
    DocumentUploadResponse,
    ParseQualityDetailsResponse,
    QualityMetricName,
)
from app.services import document_service

router = APIRouter()

MAX_FILE_SIZE = 20 * 1024 * 1024
GENERIC_PROCESSING_ERROR = "Document processing failed."
CONTROLLED_ERROR_MESSAGES = frozenset({
    "Document parsing failed.",
    "Document indexing failed.",
    "No text content extracted from file.",
    GENERIC_PROCESSING_ERROR,
})
QUALITY_METRIC_NAMES = frozenset(get_args(QualityMetricName))
PARSE_WARNINGS = frozenset(get_args(ParseWarning))


def _public_quality_details(value) -> ParseQualityDetailsResponse | None:
    if not isinstance(value, dict):
        return None
    raw_metrics = value.get("metrics")
    metrics = {
        key: metric
        for key, metric in raw_metrics.items()
        if key in QUALITY_METRIC_NAMES
        and isinstance(metric, (int, float))
        and not isinstance(metric, bool)
        and isfinite(metric)
    } if isinstance(raw_metrics, dict) else {}
    raw_warnings = value.get("warnings")
    warnings = [
        warning for warning in raw_warnings
        if isinstance(warning, str) and warning in PARSE_WARNINGS
    ] if isinstance(raw_warnings, list) else []
    return ParseQualityDetailsResponse(metrics=metrics, warnings=warnings)


def _public_provenance(document) -> dict[str, object]:
    error_message = getattr(document, "error_message", None)
    if error_message and error_message not in CONTROLLED_ERROR_MESSAGES:
        error_message = GENERIC_PROCESSING_ERROR
    return {
        "parser_name": getattr(document, "parser_name", None),
        "parser_version": getattr(document, "parser_version", None),
        "page_count": getattr(document, "page_count", None),
        "parse_quality_status": getattr(document, "parse_quality_status", None),
        "parse_quality_details": _public_quality_details(
            getattr(document, "parse_quality_details", None)
        ),
        "error_message": error_message or None,
    }


def _public_governance(document) -> dict[str, object]:
    if not hasattr(document, "family_id"):
        return {}
    family = getattr(document, "family", None)
    family_id = getattr(document, "family_id", None)
    return {
        "family_id": family_id,
        "family_name": getattr(family, "name", None),
        "version": getattr(document, "version", None),
        "index_generation": getattr(document, "index_generation", None),
        "review_status": getattr(document, "review_status", None),
        "effective_date": getattr(document, "effective_date", None),
        "expiry_date": getattr(document, "expiry_date", None),
        "owner_user_id": getattr(document, "owner_user_id", None),
        "reviewed_by_user_id": getattr(document, "reviewed_by_user_id", None),
        "reviewed_at": getattr(document, "reviewed_at", None),
        "source_type": getattr(document, "source_type", None),
        "source_ref": getattr(document, "source_ref", None),
        "chunker_version": getattr(document, "chunker_version", None),
        "embedding_provider": getattr(document, "embedding_provider", None),
        "embedding_model": getattr(document, "embedding_model", None),
        "is_current": bool(
            family_id
            and family
            and getattr(family, "current_document_id", None)
            == getattr(document, "id", None)
        ),
        "original_file_available": bool(getattr(document, "storage_key", None)),
    }


@router.post(
    "/api/v1/admin/{tenant_slug}/documents/{document_id}/review",
    response_model=DocumentReviewResponse,
)
async def review(
    tenant_slug: str,
    document_id: str,
    request: DocumentReviewRequest,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    _admin=Depends(admin_auth),
):
    try:
        document = document_service.review_document(
            db,
            tenant_id=tenant.id,
            document_id=document_id,
            decision=request.decision,
            reviewer_user_id=_admin.id if isinstance(_admin, User) else None,
        )
    except document_service.DocumentLifecycleError as error:
        status_code = 404 if str(error) == "Document not found" else 409
        raise HTTPException(status_code, str(error)) from error

    logger.info(
        "document_reviewed",
        tenant_slug=tenant_slug,
        document_id=document.id,
        decision=request.decision,
    )
    return DocumentReviewResponse(
        document_id=document.id,
        family_id=document.family_id,
        review_status=document.review_status,
        reviewed_by_user_id=document.reviewed_by_user_id,
        reviewed_at=document.reviewed_at,
        is_current=document.family.current_document_id == document.id,
    )


@router.post("/api/v1/admin/{tenant_slug}/documents/upload", status_code=201)
async def upload(
    tenant_slug: str,
    file: UploadFile = File(...),
    audience_roles: list[Literal["owner", "admin", "agent", "employee"]] = Form(default=[]),
    family_id: str | None = Form(default=None),
    family_name: str | None = Form(default=None),
    effective_date: date | None = Form(default=None),
    expiry_date: date | None = Form(default=None),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    _admin=Depends(admin_auth),
):
    if file.filename is None:
        raise HTTPException(400, "No filename provided")

    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(413, f"File too large, max {MAX_FILE_SIZE // 1024 // 1024} MB")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in {"pdf", "docx", "xlsx", "txt", "md"}:
        raise HTTPException(400, f"Unsupported file type: .{ext}")

    try:
        doc = await document_service.upload_document(
            db, tenant.id, tenant_slug, file.filename, data, audience_roles=audience_roles,
            family_id=family_id,
            family_name=family_name,
            effective_date=effective_date,
            expiry_date=expiry_date,
            owner_user_id=_admin.id if isinstance(_admin, User) else None,
        )
    except ValueError as e:
        msg = str(e)
        if "already imported" in msg:
            raise HTTPException(409, msg)
        raise HTTPException(400, msg)

    logger.info("document_uploaded", tenant_slug=tenant_slug, document_id=doc.id)
    response = DocumentUploadResponse(
        document_id=doc.id,
        filename=doc.filename,
        chunk_count=doc.chunk_count,
        status=doc.status,
        audience_roles=doc.audience_roles or [],
        **_public_provenance(doc),
        **_public_governance(doc),
    )
    return response.model_dump(exclude_unset=True)


@router.get("/api/v1/admin/{tenant_slug}/documents")
async def list_docs(
    tenant_slug: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    _admin=Depends(admin_auth),
):
    items, total = document_service.list_documents(db, tenant.id, page, page_size)
    resp_items = []
    for d in items:
        resp_items.append(DocumentResponse(
            id=d.id, tenant_id=d.tenant_id, filename=d.filename,
            file_type=d.file_type, file_size=d.file_size, file_hash=d.file_hash,
            chunk_count=d.chunk_count, status=d.status,
            audience_roles=d.audience_roles or [],
            **_public_provenance(d),
            **_public_governance(d),
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
    _admin=Depends(admin_auth),
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
                page_start=c.page_start, page_end=c.page_end,
                section_path=c.section_path, element_types=c.element_types,
                source_element_indexes=c.source_element_indexes,
                index_generation=getattr(c, "index_generation", None),
                chunker_version=getattr(c, "chunker_version", None),
                embedding_model=getattr(c, "embedding_model", None),
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
    _admin=Depends(admin_auth),
):
    doc = document_service.get_document(db, tenant.id, document_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    try:
        document_service.delete_document(
            db, tenant.id, tenant_slug, document_id
        )
    except document_service.DocumentLifecycleError as error:
        raise HTTPException(409, str(error)) from error
    logger.info("document_deleted", tenant_slug=tenant_slug, document_id=document_id)
    return {"status": "deleted"}
