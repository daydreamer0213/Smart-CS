"""Public contract for the single authenticated enterprise assistant."""

from pydantic import BaseModel, Field

from app.schemas.hr_support import HandoffDraftResponse, SourceCitation


class AssistantChatRequest(BaseModel):
    session_id: str = Field("", max_length=100)
    message: str = Field(..., min_length=1, max_length=2000)


class AssistantChatResponse(BaseModel):
    session_id: str
    reply: str
    enabled_skills: list[str]
    sources: list[SourceCitation] = Field(default_factory=list)
    pending_handoff: HandoffDraftResponse | None = None
