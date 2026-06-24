"""Admin knowledge base CRUD — Phase 1 implementation.

Endpoints:
  GET    /api/v1/admin/{tenant_slug}/knowledge       List (paginated, search, filter)
  POST   /api/v1/admin/{tenant_slug}/knowledge       Create (auto embed -> ChromaDB)
  PUT    /api/v1/admin/{tenant_slug}/knowledge/{id}  Update (re-embed)
  DELETE /api/v1/admin/{tenant_slug}/knowledge/{id}  Delete (SQL + ChromaDB)
  GET    /api/v1/admin/{tenant_slug}/categories      List categories
  POST   /api/v1/admin/{tenant_slug}/categories      Create category
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/v1/admin/{tenant_slug}/knowledge")
async def list_knowledge(tenant_slug: str):
    return {"status": "not_implemented"}


@router.post("/api/v1/admin/{tenant_slug}/knowledge")
async def create_knowledge(tenant_slug: str):
    return {"status": "not_implemented"}


@router.put("/api/v1/admin/{tenant_slug}/knowledge/{item_id}")
async def update_knowledge(tenant_slug: str, item_id: str):
    return {"status": "not_implemented"}


@router.delete("/api/v1/admin/{tenant_slug}/knowledge/{item_id}")
async def delete_knowledge(tenant_slug: str, item_id: str):
    return {"status": "not_implemented"}


@router.get("/api/v1/admin/{tenant_slug}/categories")
async def list_categories(tenant_slug: str):
    return {"status": "not_implemented"}


@router.post("/api/v1/admin/{tenant_slug}/categories")
async def create_category(tenant_slug: str):
    return {"status": "not_implemented"}
