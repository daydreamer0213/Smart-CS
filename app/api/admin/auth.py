"""Admin API key authentication."""

import hashlib
from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.tenant import AdminApiKey

router = APIRouter()


def _get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session, closing it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_admin(request: Request, db: Session = Depends(_get_db)) -> AdminApiKey:
    key = request.headers.get("X-Admin-Key", "")
    if not key:
        raise HTTPException(status_code=401, detail="Missing X-Admin-Key header")

    key_hash = hashlib.sha256(key.encode()).hexdigest()
    api_key = db.query(AdminApiKey).filter(AdminApiKey.key_hash == key_hash).first()
    if api_key is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return api_key
