"""Public contracts for the HR support handoff lifecycle."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_serializer, model_validator


class SourceCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str
    source_id: str
    title: str = ""
    excerpt: str = ""
    score: float | None = None
    page_start: int | None = None
    page_end: int | None = None
    section_path: list[str] | None = None
    element_types: list[str] | None = None

    @model_serializer(mode="wrap")
    def omit_empty_provenance(self, serializer):
        data = serializer(self)
        for field in ("page_start", "page_end", "section_path", "element_types"):
            if data.get(field) is None:
                data.pop(field, None)
        return data


class HandoffDraftResponse(BaseModel):
    id: str
    question: str
    reason: str
    sources: list[SourceCitation]
    status: str
    expires_at: datetime


class HandoffResponse(BaseModel):
    id: str
    question: str
    reason: str
    sources: list[SourceCitation]
    status: str
    assigned_user_id: str | None
    resolved_by_user_id: str | None
    resolution_note: str | None
    resolved_at: datetime | None


class HandoffStatusUpdate(BaseModel):
    status: Literal["open", "assigned", "resolved"]
    assigned_user_id: str | None = None
    resolution_note: str | None = None

    @model_validator(mode="after")
    def resolved_status_requires_note(self):
        if self.status == "resolved" and not (self.resolution_note or "").strip():
            raise ValueError("resolution_note is required when status is resolved")
        return self
