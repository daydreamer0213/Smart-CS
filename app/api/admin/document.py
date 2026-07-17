"""Admin document management endpoints."""

import structlog

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

logger = structlog.get_logger()

from app.api.admin.auth import admin_auth
from app.api.deps import get_db, get_tenant
from app.models.tenant import Tenant
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
    audience_roles: list[Literal["owner", "admin", "agent", "employee"]] = Form(default=[]),
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
        audience_roles=doc.audience_roles or [],
    )


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
            error_message=d.error_message,
            audience_roles=d.audience_roles or [],
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
    document_service.delete_document(db, tenant_slug, document_id)
    logger.info("document_deleted", tenant_slug=tenant_slug, document_id=document_id)
    return {"status": "deleted"}
