"""JWT authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.admin.auth import _verify_admin_key_for_tenant
from app.api.deps import get_current_user, get_db
from app.core.auth.security import hash_password, verify_password
from app.core.auth.token import create_access_token, create_refresh_token, decode_token
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _default_tenant_config() -> dict:
    return {
        "human_keywords": [],
        "system_prompt_append": "",
        "model_override": None,
        "cache_ttl_override": None,
        "intent_threshold_override": None,
        "handoff_enabled": True,
    }


def _user_response(user: User, tenant_slug: str) -> UserResponse:
    return UserResponse(
        id=user.id,
        tenant_id=user.tenant_id,
        tenant_slug=tenant_slug,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
    )


def _auth_response(user: User, tenant_slug: str) -> AuthResponse:
    return AuthResponse(
        access_token=create_access_token(user),
        refresh_token=create_refresh_token(user),
        user=_user_response(user, tenant_slug),
    )


def _require_tenant_admin(request: Request, tenant: Tenant, db: Session) -> None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        user = get_current_user(request, db)
        if user.tenant_id != tenant.id:
            raise HTTPException(status_code=403, detail="Tenant mismatch")
        if user.role not in ("owner", "admin"):
            raise HTTPException(status_code=403, detail="Admin or owner role required")
        return

    api_key = _verify_admin_key_for_tenant(request, tenant.slug, db)
    if api_key is not None:
        return

    raise HTTPException(status_code=401, detail="Missing tenant admin credentials")


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    request: Request, body: RegisterRequest, db: Session = Depends(get_db)
) -> AuthResponse:
    email = body.email.lower()

    if body.role == "owner":
        tenant = db.query(Tenant).filter(Tenant.slug == body.tenant_slug).first()
        if tenant is not None:
            raise HTTPException(status_code=409, detail="Tenant already exists")
        tenant = Tenant(
            slug=body.tenant_slug,
            name=body.tenant_name,
            config_json=_default_tenant_config(),
            is_active=True,
        )
        db.add(tenant)
        db.flush()
    else:
        tenant = db.query(Tenant).filter(Tenant.slug == body.tenant_slug).first()
        if tenant is None:
            raise HTTPException(status_code=404, detail="Tenant not found")
        _require_tenant_admin(request, tenant, db)

    existing = (
        db.query(User)
        .filter(User.tenant_id == tenant.id, User.email == email)
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        tenant_id=tenant.id,
        email=email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role=body.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _auth_response(user, tenant.slug)


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    tenant = db.query(Tenant).filter(Tenant.slug == body.tenant_slug).first()
    if tenant is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user = (
        db.query(User)
        .filter(User.tenant_id == tenant.id, User.email == body.email.lower())
        .first()
    )
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return _auth_response(user, tenant.slug)


@router.post("/refresh")
def refresh(body: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        payload = decode_token(body.refresh_token, "refresh")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    return TokenResponse(
        access_token=create_access_token(user),
        refresh_token=create_refresh_token(user),
    )


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserResponse:
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return _user_response(user, tenant.slug)
