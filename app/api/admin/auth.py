"""Admin authentication helpers."""

import hashlib
from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.tenant import AdminApiKey
from app.models.tenant import Tenant
from app.models.user import User
from app.api.deps import get_current_user

router = APIRouter()


def _get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session, closing it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_admin(request: Request, db: Session = Depends(_get_db)) -> AdminApiKey:
    """Verify a raw API key without checking a route tenant.

    Tenant-scoped admin routes should use admin_auth instead.
    """
    key = request.headers.get("X-Admin-Key", "")
    if not key:
        raise HTTPException(status_code=401, detail="Missing X-Admin-Key header")

    key_hash = hashlib.sha256(key.encode()).hexdigest()
    api_key = db.query(AdminApiKey).filter(AdminApiKey.key_hash == key_hash).first()
    if api_key is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return api_key


def _verify_admin_key_for_tenant(
    request: Request, tenant_slug: str, db: Session
) -> AdminApiKey | None:
    key = request.headers.get("X-Admin-Key", "")
    if not key:
        return None
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    api_key = db.query(AdminApiKey).filter(AdminApiKey.key_hash == key_hash).first()
    if api_key is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_slug}' does not exist")
    if api_key.tenant_id != tenant.id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    return api_key


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Admin or owner role required")
    return user


def require_owner(user: User = Depends(get_current_user)) -> User:
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Owner role required")
    return user


def admin_auth(
    request: Request,
    tenant_slug: str,
    db: Session = Depends(_get_db),
) -> User | AdminApiKey:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        user = get_current_user(request, db)
        if user.role not in ("owner", "admin"):
            raise HTTPException(status_code=403, detail="Admin or owner role required")
        tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
        if tenant is None:
            raise HTTPException(status_code=404, detail=f"Tenant '{tenant_slug}' does not exist")
        if user.tenant_id != tenant.id:
            raise HTTPException(status_code=403, detail="Tenant mismatch")
        return user

    api_key = _verify_admin_key_for_tenant(request, tenant_slug, db)
    if api_key is not None:
        return api_key

    raise HTTPException(status_code=401, detail="Missing admin credentials")
