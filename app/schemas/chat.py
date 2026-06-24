"""Chat schemas — request/response models for the chat API endpoint.

Covers single-turn Q&A and multi-turn conversation payloads,
including visitor_id, session_id, message content, and optional context.
"""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Placeholder for chat request schema."""
    pass


class ChatResponse(BaseModel):
    """Placeholder for chat response schema."""
    pass
