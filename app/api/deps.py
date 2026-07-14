"""FastAPI dependency injection."""

from collections.abc import Generator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.auth.token import decode_token
from app.db import SessionLocal
from app.models.tenant import Tenant
from app.models.user import User


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_tenant(db: Session = Depends(get_db), tenant_slug: str = ...) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_slug}' does not exist")
    return tenant


def _bearer_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _bearer_token(request)
    if token is None:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        payload = decode_token(token, "access")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid token")
    if user.tenant_id != payload.get("tenant_id"):
        raise HTTPException(status_code=401, detail="Invalid token")
    return user
