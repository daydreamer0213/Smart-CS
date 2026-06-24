"""Chat request/response schemas."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field("", description="Client-generated UUID, empty on first message")
    message: str = Field(..., min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    answer: str
    intent: str  # "faq" | "human"
    confidence: float
    sources: list[dict]  # [{"question": "...", "answer": "...", "score": 0.95}, ...]
    cache_hit: str  # "L1" | "L2" | "miss"
    session_id: str
    handoff: bool = False   # True if agent called handoff_to_human
