"""Customer chat endpoint — Phase 2 implementation."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db

router = APIRouter()


@router.post("/api/v1/{tenant_slug}/chat")
async def chat(request: Request, db: Session = Depends(get_db)):
    """Customer service chat endpoint. Full pipeline: cache -> intent -> retrieval -> LLM."""
    return {"status": "not_implemented"}
