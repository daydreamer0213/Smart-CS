"""FastAPI dependency injection — database session, tenant lookup, admin auth."""

from collections.abc import Generator

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.tenant import AdminApiKey, Tenant


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session, closing it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_tenant(db: Session, tenant_slug: str) -> Tenant:
    """Look up a tenant by slug; raise 404 if not found."""
    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
    if tenant is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tenant '{tenant_slug}' does not exist",
        )
    return tenant


def verify_admin(db: Session, request: Request) -> AdminApiKey:
    """Validate X-Admin-Key header against stored API keys. Raise 401 on mismatch."""
    key = request.headers.get("X-Admin-Key", "")
    if not key:
        raise HTTPException(status_code=401, detail="Missing X-Admin-Key header")

    import hashlib

    key_hash = hashlib.sha256(key.encode()).hexdigest()
    api_key = db.query(AdminApiKey).filter(AdminApiKey.key_hash == key_hash).first()
    if api_key is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return api_key
