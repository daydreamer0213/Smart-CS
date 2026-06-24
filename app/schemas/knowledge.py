"""Knowledge schemas — request/response models for knowledge base CRUD.

Covers KnowledgeItem and Category create/update/list payloads,
plus import/export formats and search query/result models.
"""

from pydantic import BaseModel


class KnowledgePlaceholder(BaseModel):
    """Placeholder — remove once real knowledge schemas are defined."""
    pass
