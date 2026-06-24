"""Health check endpoint — verifies DB and ChromaDB connectivity."""

import structlog
from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import SessionLocal
from app.config import settings

router = APIRouter()
logger = structlog.get_logger()


@router.get("/health")
async def health_check():
    checks = {"status": "ok", "version": "0.1.0"}

    # DB connectivity
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = "error"
        checks["status"] = "degraded"
        logger.error("health_db_failed", error=str(e))

    # ChromaDB connectivity (best-effort, may not be initialized in tests)
    try:
        from app.core.retrieval_module import get_vector_store
        vs = get_vector_store()
        if vs is not None:
            vs._client.heartbeat()
            checks["chromadb"] = "ok"
    except Exception:
        checks["chromadb"] = "not_initialized"

    return checks
