"""Document upload/management schemas."""

from pydantic import BaseModel, Field


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
    parse_quality_details: dict[str, object] | None = None
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
    parse_quality_details: dict[str, object] | None = None
    error_message: str | None = None
