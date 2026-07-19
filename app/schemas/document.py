"""Document upload/management schemas."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.parsing.contracts import ParseWarning


QualityMetricName = Literal[
    "page_count",
    "usable_text_pages",
    "empty_pages",
    "character_count",
    "table_count",
    "heading_count",
    "ocr_pages",
    "elapsed_ms",
    "ocr_confidence",
]


class ParseQualityDetailsResponse(BaseModel):
    metrics: dict[QualityMetricName, int | float] = Field(default_factory=dict)
    warnings: list[ParseWarning] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class DocumentResponse(BaseModel):
    id: str
    tenant_id: str
    filename: str
    file_type: str
    file_size: int
    file_hash: str
    chunk_count: int
    status: str
    error_message: str | None
    audience_roles: list[str]
    parser_name: str | None = None
    parser_version: str | None = None
    page_count: int | None = None
    parse_quality_status: str | None = None
    parse_quality_details: ParseQualityDetailsResponse | None = None
    family_id: str | None = None
    family_name: str | None = None
    version: int | None = None
    index_generation: int | None = None
    review_status: str | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    owner_user_id: str | None = None
    reviewed_by_user_id: str | None = None
    reviewed_at: datetime | None = None
    source_type: str | None = None
    source_ref: str | None = None
    chunker_version: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    is_current: bool = False
    original_file_available: bool = False
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class DocumentChunkResponse(BaseModel):
    id: str
    chunk_index: int
    content: str
    token_count: int
    keywords: str | None
    status: str
    page_start: int | None = None
    page_end: int | None = None
    section_path: list[str] | None = None
    element_types: list[str] | None = None
    source_element_indexes: list[int] | None = None
    index_generation: int | None = None
    chunker_version: str | None = None
    embedding_model: str | None = None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    chunk_count: int
    status: str
    audience_roles: list[str]
    parser_name: str | None = None
    parser_version: str | None = None
    page_count: int | None = None
    parse_quality_status: str | None = None
    parse_quality_details: ParseQualityDetailsResponse | None = None
    error_message: str | None = None
    family_id: str | None = None
    family_name: str | None = None
    version: int | None = None
    index_generation: int | None = None
    review_status: str | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    owner_user_id: str | None = None
    reviewed_by_user_id: str | None = None
    reviewed_at: datetime | None = None
    source_type: str | None = None
    source_ref: str | None = None
    chunker_version: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    is_current: bool = False
    original_file_available: bool = False
