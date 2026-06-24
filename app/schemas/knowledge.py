"""Knowledge base CRUD schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class KnowledgeCreate(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    answer: str = Field(..., min_length=1, max_length=5000)
    keywords: str | None = Field(None, max_length=500)
    category_id: str | None = None


class KnowledgeUpdate(BaseModel):
    question: str | None = Field(None, min_length=1, max_length=2000)
    answer: str | None = Field(None, min_length=1, max_length=5000)
    keywords: str | None = Field(None, max_length=500)
    category_id: str | None = None
    status: Literal["active", "draft", "archived"] | None = None


class KnowledgeItemResponse(BaseModel):
    id: str
    tenant_id: str
    category_id: str | None
    question: str
    answer: str
    keywords: str | None
    embedding_id: str | None
    status: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class KnowledgeListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    q: str | None = None
    category_id: str | None = None
    status: Literal["active", "draft", "archived"] | None = None


class KnowledgeListResponse(BaseModel):
    items: list[KnowledgeItemResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=1000)
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    sort_order: int | None = None


class CategoryResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: str
    sort_order: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
