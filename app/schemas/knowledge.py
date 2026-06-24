"""Knowledge schemas — request/response models for knowledge base CRUD.

Covers KnowledgeItem and Category create/update/list payloads,
plus import/export formats and search query/result models.
"""

from pydantic import BaseModel


class KnowledgeCreate(BaseModel):
    """Placeholder for knowledge item creation schema."""
    pass


class KnowledgeUpdate(BaseModel):
    """Placeholder for knowledge item update schema."""
    pass


class KnowledgeResponse(BaseModel):
    """Placeholder for knowledge item response schema."""
    pass
