"""FastAPI dependency injection."""

from collections.abc import Generator

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.tenant import Tenant


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
