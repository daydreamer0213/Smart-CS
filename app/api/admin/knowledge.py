"""Admin knowledge base CRUD."""

import structlog

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

logger = structlog.get_logger()

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
    item = knowledge_service.create_knowledge(db, tenant.id, body, tenant_slug=tenant_slug)
    logger.info("admin_knowledge_created", tenant_slug=tenant_slug, item_id=item.id)
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
    updated = knowledge_service.update_knowledge(db, item_id, body, tenant_slug=tenant_slug)
    logger.info("admin_knowledge_updated", tenant_slug=tenant_slug, item_id=item_id)
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
    knowledge_service.delete_knowledge(db, item_id, tenant_slug=tenant_slug)
    logger.info("admin_knowledge_deleted", tenant_slug=tenant_slug, item_id=item_id)
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
        item = knowledge_service.create_knowledge(db, tenant.id, data, tenant_slug=tenant_slug)
        items.append(_item_to_response(item))
    logger.info("admin_knowledge_batch_imported", tenant_slug=tenant_slug, count=len(items))
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
