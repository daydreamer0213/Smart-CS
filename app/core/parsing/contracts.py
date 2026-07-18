from typing import Annotated, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator, model_validator

ElementType = Literal["title", "heading", "paragraph", "list", "table", "image"]
QualityStatus = Literal["passed", "review_required", "failed"]
ParseWarning = Literal[
    "advanced_parser_incomplete",
    "encrypted_input",
    "indexing_blocked",
    "low_ocr_confidence",
    "missing_page_coverage",
    "parser_exception",
]
MetadataScalar = str | int | float | bool | None


class ParseQuality(BaseModel):
    status: QualityStatus = "passed"
    metrics: dict[str, int | float] = Field(default_factory=dict)
    warnings: list[ParseWarning] = Field(default_factory=list)


class ParsedElement(BaseModel):
    text: str
    element_type: ElementType
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    section_path: list[str] = Field(default_factory=list)
    table_markdown: str | None = None
    metadata: dict[str, MetadataScalar] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def strip_non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must not be empty")
        return value

    @model_validator(mode="after")
    def validate_page_span(self):
        if self.page_start is None and self.page_end is not None:
            raise ValueError("page_start is required when page_end is set")
        if self.page_start is not None and self.page_end is None:
            self.page_end = self.page_start
        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_end < self.page_start
        ):
            raise ValueError("page_end must be greater than or equal to page_start")
        return self


class ParsedDocument(BaseModel):
    parser_name: str = Field(min_length=1)
    parser_version: str = Field(min_length=1)
    page_count: int = Field(ge=0)
    elements: list[ParsedElement]
    quality: ParseQuality = Field(default_factory=ParseQuality)
    metadata: dict[str, MetadataScalar] = Field(default_factory=dict)

    @property
    def plain_text(self) -> str:
        return "\n\n".join(element.text for element in self.elements)

    @model_validator(mode="after")
    def validate_page_bounds(self):
        for element in self.elements:
            if element.page_end is not None and element.page_end > self.page_count:
                raise ValueError("element page span exceeds page_count")
        return self


class KnowledgeChunk(BaseModel):
    content: str = Field(min_length=1)
    contextualized_content: str = Field(min_length=1)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    section_path: list[str] = Field(default_factory=list)
    element_types: list[ElementType] = Field(default_factory=list)
    source_element_indexes: list[Annotated[int, Field(ge=0)]] = Field(default_factory=list)
    token_count: int = Field(ge=0)
    metadata: dict[str, MetadataScalar] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_page_span(self):
        if self.page_start is None and self.page_end is not None:
            raise ValueError("page_start is required when page_end is set")
        if self.page_start is not None and self.page_end is None:
            self.page_end = self.page_start
        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_end < self.page_start
        ):
            raise ValueError("page_end must be greater than or equal to page_start")
        return self


@runtime_checkable
class DocumentParser(Protocol):
    name: str
    version: str

    def supports(self, filename: str) -> bool: ...

    def parse(self, filename: str, data: bytes) -> ParsedDocument: ...
