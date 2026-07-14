# Phase 1.2 JWT 认证 — Implementation Plan

> Historical implementation plan. JWT auth has been completed, and SmartCS has
> since evolved into the enterprise employee Agent + controlled CRM workflow
> positioning. Use `README.md` and `CONTINUE.md` for the current project state.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 添加 JWT 认证体系（用户注册/登录/刷新），替换 API Key 作为人类管理员认证方式，保留 API Key 给 M2M/脚本调用。

**Architecture:** 新增 User 模型、`core/auth/` 库（token 签发+密码哈希）、`/api/v1/auth/` 端点。通过 `get_current_user` 依赖注入 JWT 认证，`require_admin`/`require_owner` 做角色检查。现有 `verify_admin` 保留不变，两条认证线独立运作。

**Tech Stack:** python-jose[cryptography], passlib[bcrypt]

**Spec:** `docs/superpowers/specs/2026-06-24-jwt-auth-design.md`

## Global Constraints

- 所有 model ID 为 `String(36)` UUID，继承 `Base, TimestampMixin`
- API 错误格式: `{"error": {"code": "...", "message": "..."}, "request_id": "..."}`
- 密码 >= 8 字符，至少 1 字母 + 1 数字
- bcrypt cost factor 12
- access token 15min, refresh token 7d
- JWT algorithm HS256
- 测试优先，每步改完立刻跑 pytest
- 现有 94 个测试必须保持通过
- 新增依赖: `python-jose[cryptography]`, `passlib[bcrypt]`, `email-validator`

---

### Task 1: 依赖安装 + Config 扩展

**Files:**
- Modify: `D:\2026.07.09\AAA\smart-cs\requirements.txt`
- Modify: `D:\2026.07.09\AAA\smart-cs\app\config.py`

**Interfaces:**
- Produces: `settings.jwt_secret: str`, `settings.jwt_algorithm: str`, `settings.access_token_expire_minutes: int`, `settings.refresh_token_expire_days: int`

- [ ] **Step 1: 添加依赖到 requirements.txt**

```bash
echo "python-jose[cryptography]>=3.3.0" >> requirements.txt
echo "passlib[bcrypt]>=1.7.4" >> requirements.txt
echo "email-validator>=2.0.0" >> requirements.txt
```

- [ ] **Step 2: 安装新依赖**

```bash
D:/2026.07.09/conda/Scripts/conda.exe activate smart-cs && pip install python-jose[cryptography] passlib[bcrypt] email-validator --cache-dir D:/2026.07.09/smartcs-cache/pip/
```

- [ ] **Step 3: 在 config.py 添加 JWT 配置字段**

In `D:\2026.07.09\AAA\smart-cs\app\config.py`, add after `agent_stream_enabled`:

```python
    # JWT Auth
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
```

- [ ] **Step 4: 验证 config 加载**

```bash
D:/2026.07.09/conda-envs/smart-cs/python.exe -c "from app.config import settings; print(settings.jwt_algorithm); print(settings.access_token_expire_minutes)"
```

Expected output:
```
HS256
15
```

- [ ] **Step 5: 验证现有 94 个测试仍然通过**

```bash
D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/ -v --tb=short 2>&1 | tail -5
```

Expected: `94 passed`

- [ ] **Step 6: Commit**

```bash
git add requirements.txt app/config.py
git commit -m "chore: add JWT dependencies and config fields

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: User 模型

**Files:**
- Create: `D:\2026.07.09\AAA\smart-cs\app\models\user.py`
- Modify: `D:\2026.07.09\AAA\smart-cs\app\models\__init__.py`

**Interfaces:**
- Produces: `User` class with columns: `id`, `email`, `password_hash`, `display_name`, `role`, `is_active`, `tenant_id`, `created_at`, `updated_at`; relationship `tenant` → Tenant

- [ ] **Step 1: 写模型级测试**

Create `D:\2026.07.09\AAA\smart-cs\tests\test_auth.py`:

```python
"""Tests for JWT auth — user model, security, token, and API endpoints."""
import pytest
from sqlalchemy import inspect

from app.models.user import User
from app.models.tenant import Tenant


class TestUserModel:
    def test_user_table_created(self, engine):
        """User table exists in the database."""
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "users" in tables

    def test_user_columns(self, engine):
        """All expected columns exist."""
        inspector = inspect(engine)
        cols = {c["name"] for c in inspector.get_columns("users")}
        expected = {"id", "email", "password_hash", "display_name", "role",
                    "is_active", "tenant_id", "created_at", "updated_at"}
        assert expected.issubset(cols)

    def test_create_user(self, db, test_tenant):
        """Can create a User with valid fields."""
        from app.core.auth.security import hash_password

        user = User(
            email="test@example.com",
            password_hash=hash_password("password1"),
            display_name="Test User",
            role="admin",
            tenant_id=test_tenant.id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        assert user.id is not None
        assert user.email == "test@example.com"
        assert user.role == "admin"
        assert user.is_active is True
        assert user.tenant_id == test_tenant.id

    def test_user_email_unique(self, db, test_tenant):
        """Duplicate email raises IntegrityError."""
        from app.core.auth.security import hash_password

        u1 = User(
            email="dup@example.com",
            password_hash=hash_password("password1"),
            display_name="U1",
            role="agent",
            tenant_id=test_tenant.id,
        )
        db.add(u1)
        db.commit()

        u2 = User(
            email="dup@example.com",
            password_hash=hash_password("password1"),
            display_name="U2",
            role="agent",
            tenant_id=test_tenant.id,
        )
        db.add(u2)
        with pytest.raises(Exception):  # IntegrityError
            db.commit()

    def test_user_tenant_relationship(self, db, test_tenant):
        """User.tenant navigates to the Tenant."""
        from app.core.auth.security import hash_password

        user = User(
            email="rel@example.com",
            password_hash=hash_password("password1"),
            display_name="Rel User",
            role="owner",
            tenant_id=test_tenant.id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        assert user.tenant is not None
        assert user.tenant.slug == test_tenant.slug
```

- [ ] **Step 2: 运行测试 — 预期失败（User 模型不存在）**

```bash
D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/test_auth.py::TestUserModel -v --tb=short 2>&1 | tail -20
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.user'`

- [ ] **Step 3: 创建 User 模型**

Create `D:\2026.07.09\AAA\smart-cs\app\models\user.py`:

```python
from sqlalchemy import Boolean, Column, ForeignKey, String
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    display_name = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False, default="agent")
    is_active = Column(Boolean, default=True, nullable=False)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)

    tenant = relationship("Tenant")
```

- [ ] **Step 4: 注册到 models/__init__.py**

In `D:\2026.07.09\AAA\smart-cs\app\models\__init__.py`, add after the `from app.models.knowledge import` line:

```python
from app.models.user import User
```

And add `"User"` to `__all__` list.

- [ ] **Step 5: 运行 User 模型测试**

```bash
D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/test_auth.py::TestUserModel -v --tb=short
```

Expected: 4 passed

- [ ] **Step 6: 验证回归 — 现有测试仍全过**

```bash
D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/ -v --tb=short 2>&1 | tail -5
```

Expected: `98 passed` (94 existing + 4 new)

- [ ] **Step 7: Commit**

```bash
git add app/models/user.py app/models/__init__.py tests/test_auth.py
git commit -m "feat: add User model with tenant relationship

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: Auth Schemas

**Files:**
- Create: `D:\2026.07.09\AAA\smart-cs\app\schemas\auth.py`

**Interfaces:**
- Produces: `RegisterRequest`, `LoginRequest`, `RefreshRequest`, `UserResponse`, `TokenResponse` Pydantic models

- [ ] **Step 1: 写 schema 测试**

Append to `D:\2026.07.09\AAA\smart-cs\tests\test_auth.py`:

```python
import re
from app.schemas.auth import (
    RegisterRequest, LoginRequest, RefreshRequest, UserResponse, TokenResponse,
)


class TestAuthSchemas:
    def test_register_request_owner_valid(self):
        req = RegisterRequest(
            email="owner@test.com",
            password="pass12345",
            display_name="Owner",
            role="owner",
            tenant_slug="my-shop",
            tenant_name="My Shop",
        )
        assert req.email == "owner@test.com"
        assert req.role == "owner"

    def test_register_request_owner_missing_tenant_name(self):
        with pytest.raises(ValueError):
            RegisterRequest(
                email="o@test.com",
                password="pass12345",
                display_name="O",
                role="owner",
                tenant_slug="my-shop",
                # missing tenant_name
            )

    def test_register_request_agent_missing_tenant_slug(self):
        with pytest.raises(ValueError):
            RegisterRequest(
                email="a@test.com",
                password="pass12345",
                display_name="A",
                role="agent",
                # missing tenant_slug
            )

    def test_register_request_short_password(self):
        with pytest.raises(ValueError):
            RegisterRequest(
                email="a@test.com",
                password="short",
                display_name="A",
                role="agent",
                tenant_slug="demo",
            )

    def test_login_request_valid(self):
        req = LoginRequest(email="u@test.com", password="pass1234")
        assert req.email == "u@test.com"

    def test_refresh_request_valid(self):
        req = RefreshRequest(refresh_token="eyJ...")
        assert req.refresh_token == "eyJ..."

    def test_token_response_structure(self):
        resp = TokenResponse(
            user=UserResponse(
                id="uid", email="u@t.com", display_name="U",
                role="agent", tenant_slug="demo",
            ),
            access_token="at", refresh_token="rt",
        )
        data = resp.model_dump()
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == "u@t.com"
```

- [ ] **Step 2: 运行测试 — 预期失败**

```bash
D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/test_auth.py::TestAuthSchemas -v --tb=short 2>&1 | tail -20
```

Expected: FAIL — cannot import `app.schemas.auth`

- [ ] **Step 3: 创建 auth schemas**

Create `D:\2026.07.09\AAA\smart-cs\app\schemas\auth.py`:

```python
"""Auth schemas — register, login, refresh, token response."""
import re

from pydantic import BaseModel, Field, model_validator


def _validate_password(v: str) -> str:
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters")
    if not re.search(r"[a-zA-Z]", v):
        raise ValueError("Password must contain at least one letter")
    if not re.search(r"[0-9]", v):
        raise ValueError("Password must contain at least one digit")
    return v


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=100)
    role: str = Field(default="agent", pattern=r"^(owner|admin|agent)$")
    tenant_slug: str | None = Field(default=None, max_length=50)
    tenant_name: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _check_role_fields(self):
        if self.role == "owner":
            if not self.tenant_slug:
                raise ValueError("owner registration requires tenant_slug")
            if not self.tenant_name:
                raise ValueError("owner registration requires tenant_name")
        elif self.role in ("admin", "agent"):
            if not self.tenant_slug:
                raise ValueError("admin/agent registration requires tenant_slug")
        _validate_password(self.password)
        return self


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str
    role: str
    tenant_slug: str

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    user: UserResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
```

- [ ] **Step 4: 运行 schema 测试**

```bash
D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/test_auth.py::TestAuthSchemas -v --tb=short
```

Expected: 7 passed

- [ ] **Step 5: 验证回归**

```bash
D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/ -v --tb=short 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
git add app/schemas/auth.py tests/test_auth.py
git commit -m "feat: add auth request/response schemas

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: 密码哈希（security.py）

**Files:**
- Create: `D:\2026.07.09\AAA\smart-cs\app\core\auth\__init__.py`
- Create: `D:\2026.07.09\AAA\smart-cs\app\core\auth\security.py`

**Interfaces:**
- Produces: `hash_password(password: str) -> str`, `verify_password(plain_password: str, hashed: str) -> bool`

- [ ] **Step 1: 写 security 测试**

Append to `D:\2026.07.09\AAA\smart-cs\tests\test_auth.py`:

```python
class TestPasswordHashing:
    def test_hash_and_verify(self):
        from app.core.auth.security import hash_password, verify_password

        pw = "mySecret123"
        hashed = hash_password(pw)
        assert hashed != pw
        assert verify_password(pw, hashed) is True

    def test_verify_wrong_password(self):
        from app.core.auth.security import hash_password, verify_password

        hashed = hash_password("correct1")
        assert verify_password("wrongPassword1", hashed) is False

    def test_hash_is_deterministic_for_verify(self):
        from app.core.auth.security import hash_password, verify_password

        hashed = hash_password("test1234")
        # Same hash should verify its own password
        assert verify_password("test1234", hashed) is True
        # Different password should fail
        assert verify_password("test1235", hashed) is False
```

- [ ] **Step 2: 运行测试 — 预期失败**

```bash
D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/test_auth.py::TestPasswordHashing -v --tb=short 2>&1 | tail -20
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 创建 security.py**

Create `D:\2026.07.09\AAA\smart-cs\app\core\auth\__init__.py` (empty file).

Create `D:\2026.07.09\AAA\smart-cs\app\core\auth\security.py`:

```python
"""Password hashing with bcrypt via passlib."""

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=12, deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed: str) -> bool:
    return _pwd_context.verify(plain_password, hashed)
```

- [ ] **Step 4: 运行 security 测试**

```bash
D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/test_auth.py::TestPasswordHashing -v --tb=short
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add app/core/auth/__init__.py app/core/auth/security.py tests/test_auth.py
git commit -m "feat: add password hashing with bcrypt

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: JWT Token（token.py）

**Files:**
- Create: `D:\2026.07.09\AAA\smart-cs\app\core\auth\token.py`

**Interfaces:**
- Produces: `create_access_token(user_id, tenant_id, role) -> str`, `create_refresh_token(user_id, tenant_id, role) -> str`, `decode_token(token, expected_type) -> dict`

- [ ] **Step 1: 设置 JWT_SECRET 用于测试**

In `D:\2026.07.09\AAA\smart-cs\tests\conftest.py`, after the `settings.llm_api_key` patch, add:

```python
# Set a test JWT secret so token functions work without .env
if not settings.jwt_secret:
    settings.jwt_secret = "test-secret-key-for-pytest"
```

- [ ] **Step 2: 写 token 测试**

Append to `D:\2026.07.09\AAA\smart-cs\tests\test_auth.py`:

```python
from jose import JWTError


class TestJwtToken:
    def test_create_and_decode_access_token(self):
        from app.core.auth.token import create_access_token, decode_token

        token = create_access_token("user-1", "tenant-1", "admin")
        payload = decode_token(token, expected_type="access")

        assert payload["sub"] == "user-1"
        assert payload["tenant_id"] == "tenant-1"
        assert payload["role"] == "admin"
        assert payload["type"] == "access"
        assert "jti" in payload
        assert "exp" in payload
        assert "iat" in payload

    def test_create_and_decode_refresh_token(self):
        from app.core.auth.token import create_refresh_token, decode_token

        token = create_refresh_token("user-2", "tenant-2", "agent")
        payload = decode_token(token, expected_type="refresh")

        assert payload["sub"] == "user-2"
        assert payload["type"] == "refresh"

    def test_refresh_token_rejected_as_access(self):
        from app.core.auth.token import create_refresh_token, decode_token

        token = create_refresh_token("u", "t", "agent")
        with pytest.raises(JWTError):
            decode_token(token, expected_type="access")

    def test_access_token_rejected_as_refresh(self):
        from app.core.auth.token import create_access_token, decode_token

        token = create_access_token("u", "t", "agent")
        with pytest.raises(JWTError):
            decode_token(token, expected_type="refresh")

    def test_invalid_token_raises(self):
        from app.core.auth.token import decode_token

        with pytest.raises(JWTError):
            decode_token("invalid.token.here", expected_type="access")

    def test_expired_token_raises(self):
        from app.core.auth.token import create_access_token, decode_token
        from app.config import settings
        from datetime import timedelta

        # Temporarily set expiry to negative
        original = settings.access_token_expire_minutes
        settings.access_token_expire_minutes = -1
        try:
            token = create_access_token("u", "t", "agent")
            with pytest.raises(JWTError):
                decode_token(token, expected_type="access")
        finally:
            settings.access_token_expire_minutes = original
```

- [ ] **Step 3: 运行测试 — 预期失败**

```bash
D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/test_auth.py::TestJwtToken -v --tb=short 2>&1 | tail -20
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.auth.token'`

- [ ] **Step 4: 创建 token.py**

Create `D:\2026.07.09\AAA\smart-cs\app\core\auth\token.py`:

```python
"""JWT token creation and verification using python-jose."""

import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config import settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: str, tenant_id: str, role: str) -> str:
    now = _utcnow()
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "jti": str(uuid.uuid4()),
        "type": "access",
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str, tenant_id: str, role: str) -> str:
    now = _utcnow()
    expire = now + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "jti": str(uuid.uuid4()),
        "type": "refresh",
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: str = "access") -> dict:
    payload = jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    if payload.get("type") != expected_type:
        raise JWTError(f"Expected token type '{expected_type}', got '{payload.get('type')}'")
    return payload
```

- [ ] **Step 5: 运行 token 测试**

```bash
D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/test_auth.py::TestJwtToken -v --tb=short
```

Expected: 6 passed

- [ ] **Step 6: 验证回归**

```bash
D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/ -v --tb=short 2>&1 | tail -5
```

- [ ] **Step 7: Commit**

```bash
git add app/core/auth/token.py tests/test_auth.py tests/conftest.py
git commit -m "feat: add JWT token creation and verification

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: Auth API 端点

**Files:**
- Create: `D:\2026.07.09\AAA\smart-cs\app\api\auth.py`

**Interfaces:**
- Produces: `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`
- Consumes: `RegisterRequest`, `LoginRequest`, `RefreshRequest`, `TokenResponse`, `hash_password`, `verify_password`, `create_access_token`, `create_refresh_token`, `decode_token`, `User`

- [ ] **Step 1: 写 API 集成测试**

Append to `D:\2026.07.09\AAA\smart-cs\tests\test_auth.py`:

```python
class TestAuthAPI:
    async def test_register_owner_creates_tenant(self, client, db):
        resp = await client.post("/api/v1/auth/register", json={
            "email": "owner@newshop.com",
            "password": "ownerpass1",
            "display_name": "Shop Owner",
            "role": "owner",
            "tenant_slug": "newshop",
            "tenant_name": "New Shop",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["user"]["email"] == "owner@newshop.com"
        assert data["user"]["role"] == "owner"
        assert data["user"]["tenant_slug"] == "newshop"
        assert len(data["access_token"]) > 0
        assert len(data["refresh_token"]) > 0
        assert data["token_type"] == "bearer"

    async def test_register_admin_binds_to_existing_tenant(self, client, test_tenant):
        resp = await client.post("/api/v1/auth/register", json={
            "email": "admin@existing.com",
            "password": "adminpass1",
            "display_name": "Admin",
            "role": "admin",
            "tenant_slug": test_tenant.slug,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["user"]["tenant_slug"] == test_tenant.slug
        assert data["user"]["role"] == "admin"

    async def test_register_duplicate_email(self, client, test_tenant):
        await client.post("/api/v1/auth/register", json={
            "email": "dup@test.com",
            "password": "password1",
            "display_name": "First",
            "role": "agent",
            "tenant_slug": test_tenant.slug,
        })
        resp = await client.post("/api/v1/auth/register", json={
            "email": "dup@test.com",
            "password": "password1",
            "display_name": "Second",
            "role": "agent",
            "tenant_slug": test_tenant.slug,
        })
        assert resp.status_code == 409

    async def test_login_success(self, client, test_tenant):
        # Register first
        await client.post("/api/v1/auth/register", json={
            "email": "login@test.com",
            "password": "loginpass1",
            "display_name": "Login User",
            "role": "agent",
            "tenant_slug": test_tenant.slug,
        })
        # Then login
        resp = await client.post("/api/v1/auth/login", json={
            "email": "login@test.com",
            "password": "loginpass1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["email"] == "login@test.com"
        assert len(data["access_token"]) > 0

    async def test_login_wrong_password(self, client, test_tenant):
        await client.post("/api/v1/auth/register", json={
            "email": "wrongpw@test.com",
            "password": "rightpass1",
            "display_name": "WP",
            "role": "agent",
            "tenant_slug": test_tenant.slug,
        })
        resp = await client.post("/api/v1/auth/login", json={
            "email": "wrongpw@test.com",
            "password": "wrongpassword1",
        })
        assert resp.status_code == 401

    async def test_login_nonexistent_email(self, client):
        resp = await client.post("/api/v1/auth/login", json={
            "email": "noone@test.com",
            "password": "whatever1",
        })
        assert resp.status_code == 401

    async def test_login_disabled_user(self, client, test_tenant, db):
        from app.models.user import User
        from app.core.auth.security import hash_password

        user = User(
            email="disabled@test.com",
            password_hash=hash_password("password1"),
            display_name="Disabled",
            role="agent",
            is_active=False,
            tenant_id=test_tenant.id,
        )
        db.add(user)
        db.commit()

        resp = await client.post("/api/v1/auth/login", json={
            "email": "disabled@test.com",
            "password": "password1",
        })
        assert resp.status_code == 401

    async def test_refresh_success(self, client, test_tenant):
        reg = await client.post("/api/v1/auth/register", json={
            "email": "refresh@test.com",
            "password": "refreshpass1",
            "display_name": "Refresh",
            "role": "agent",
            "tenant_slug": test_tenant.slug,
        })
        refresh_token = reg.json()["refresh_token"]

        resp = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["access_token"]) > 0
        assert len(data["refresh_token"]) > 0
        # Old refresh should be rotated (new token != old token)
        assert data["refresh_token"] != refresh_token

    async def test_refresh_with_access_token_fails(self, client, test_tenant):
        reg = await client.post("/api/v1/auth/register", json={
            "email": "acctoken@test.com",
            "password": "password1",
            "display_name": "AT",
            "role": "agent",
            "tenant_slug": test_tenant.slug,
        })
        access_token = reg.json()["access_token"]

        resp = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": access_token,
        })
        assert resp.status_code == 401

    async def test_refresh_expired_token(self, client):
        """An already-expired refresh token returns 401."""
        resp = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": "invalid.refresh.token",
        })
        assert resp.status_code == 401
```

- [ ] **Step 2: 运行测试 — 预期失败**

```bash
D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/test_auth.py::TestAuthAPI -v --tb=short 2>&1 | tail -20
```

Expected: FAIL — 404 for the endpoints

- [ ] **Step 3: 创建 auth API router**

Create `D:\2026.07.09\AAA\smart-cs\app\api\auth.py`:

```python
"""Auth endpoints — register, login, refresh."""

import structlog

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.auth.security import hash_password, verify_password
from app.core.auth.token import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/auth")


def _build_token_response(user: User, tenant_slug: str) -> TokenResponse:
    access = create_access_token(user.id, user.tenant_id, user.role)
    refresh = create_refresh_token(user.id, user.tenant_id, user.role)
    return TokenResponse(
        user=UserResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            tenant_slug=tenant_slug,
        ),
        access_token=access,
        refresh_token=refresh,
    )


@router.post("/register", status_code=201, response_model=TokenResponse)
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    # Check duplicate email
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(409, detail="Email already registered")

    # Resolve tenant
    if body.role == "owner":
        if db.query(Tenant).filter(Tenant.slug == body.tenant_slug).first():
            raise HTTPException(409, detail="Tenant slug already exists")
        tenant = Tenant(slug=body.tenant_slug, name=body.tenant_name, config_json={})
        db.add(tenant)
        db.flush()
    else:
        tenant = db.query(Tenant).filter(Tenant.slug == body.tenant_slug).first()
        if tenant is None:
            raise HTTPException(404, detail="Tenant not found")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role=body.role,
        tenant_id=tenant.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return _build_token_response(user, tenant.slug)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if user is None:
        raise HTTPException(401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(401, detail="Account is disabled")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(401, detail="Invalid email or password")

    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    return _build_token_response(user, tenant.slug if tenant else "unknown")


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    from jose import JWTError

    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
    except JWTError:
        raise HTTPException(401, detail="Invalid or expired refresh token")

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if user is None or not user.is_active:
        raise HTTPException(401, detail="User not found or disabled")

    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    return _build_token_response(user, tenant.slug if tenant else "unknown")
```

- [ ] **Step 4: 注册 auth router 到 main.py**

In `D:\2026.07.09\AAA\smart-cs\app\main.py`:
- Add import: `from app.api.auth import router as auth_router` (after other router imports)
- Add: `app.include_router(auth_router)` (after other include_router calls)

- [ ] **Step 5: 运行 API 测试**

```bash
D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/test_auth.py::TestAuthAPI -v --tb=short
```

Expected: 10 passed

- [ ] **Step 6: 验证回归**

```bash
D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/ -v --tb=short 2>&1 | tail -5
```

- [ ] **Step 7: Commit**

```bash
git add app/api/auth.py app/main.py tests/test_auth.py
git commit -m "feat: add auth API endpoints (register/login/refresh)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: Auth 依赖（get_current_user）

**Files:**
- Modify: `D:\2026.07.09\AAA\smart-cs\app\api\deps.py`

**Interfaces:**
- Produces: `get_current_user(request: Request, db: Session) -> User`
- Consumes: `decode_token`, `User`

- [ ] **Step 1: 写依赖测试**

Append to `D:\2026.07.09\AAA\smart-cs\tests\test_auth.py`:

```python
class TestGetCurrentUser:
    async def test_valid_token_returns_user(self, client, test_tenant):
        # Register a user first
        reg = await client.post("/api/v1/auth/register", json={
            "email": "dep@test.com",
            "password": "deppass1",
            "display_name": "Dep User",
            "role": "agent",
            "tenant_slug": test_tenant.slug,
        })
        token = reg.json()["access_token"]

        # Hit an endpoint that uses get_current_user — we'll add a test endpoint
        resp = await client.get("/api/v1/auth/me", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "dep@test.com"

    async def test_no_token_returns_401(self, client):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    async def test_invalid_token_returns_401(self, client):
        resp = await client.get("/api/v1/auth/me", headers={
            "Authorization": "Bearer invalid.token",
        })
        assert resp.status_code == 401

    async def test_malformed_auth_header_returns_401(self, client):
        resp = await client.get("/api/v1/auth/me", headers={
            "Authorization": "NoBearer",
        })
        assert resp.status_code == 401

    async def test_expired_token_returns_401(self, client):
        from app.core.auth.token import create_access_token
        from app.config import settings

        original = settings.access_token_expire_minutes
        settings.access_token_expire_minutes = -1
        try:
            token = create_access_token("u", "t", "agent")
        finally:
            settings.access_token_expire_minutes = original

        resp = await client.get("/api/v1/auth/me", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp.status_code == 401
```

- [ ] **Step 2: 添加 /me 测试端点 + get_current_user**

In `D:\2026.07.09\AAA\smart-cs\app\api\auth.py`, add after the existing imports:

```python
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer()
```

And add endpoint:

```python
@router.get("/me")
def me(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "tenant_slug": tenant.slug if tenant else "unknown",
    }
```

In `D:\2026.07.09\AAA\smart-cs\app\api\deps.py`, add:

```python
from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.auth.token import decode_token
from app.models.user import User

_security = HTTPBearer()


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Extract and validate JWT from Authorization header, return User."""
    # HTTPBearer already raises 401 if header is missing or malformed
    credentials = _security(request)
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account is disabled")
    return user
```

Note: This requires updating the imports at the top of `deps.py`. The existing imports are `from collections.abc import Generator` and `from fastapi import Depends, HTTPException`. Change to:

```python
from collections.abc import Generator

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.core.auth.token import decode_token
from app.models.tenant import Tenant
from app.models.user import User
```

- [ ] **Step 3: 运行依赖测试**

```bash
D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/test_auth.py::TestGetCurrentUser -v --tb=short
```

Expected: 5 passed

- [ ] **Step 4: 验证回归**

```bash
D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/ -v --tb=short 2>&1 | tail -5
```

- [ ] **Step 5: Commit**

```bash
git add app/api/deps.py app/api/auth.py tests/test_auth.py
git commit -m "feat: add get_current_user dependency + /me endpoint

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 8: Admin 角色检查（require_admin / require_owner）

**Files:**
- Modify: `D:\2026.07.09\AAA\smart-cs\app\api\admin\auth.py`

**Interfaces:**
- Produces: `require_admin(db, request) -> User`, `require_owner(db, request) -> User`
- Consumes: `get_current_user`

- [ ] **Step 1: 写角色检查测试**

Append to `D:\2026.07.09\AAA\smart-cs\tests\test_auth.py`:

```python
class TestAdminRoleCheck:
    async def test_admin_can_access_admin_route(self, client, test_tenant):
        from app.core.auth.token import create_access_token
        from app.models.user import User
        from app.core.auth.security import hash_password
        from sqlalchemy.orm import Session

        db = next(iter([client]))  # won't work — need db session
```

Wait, this needs a proper approach. Let me think again...

The `client` fixture provides an AsyncClient. I can't easily get a db session there. Instead, I'll test role checks through the actual admin API once we wire them up.

Let me simplify this test class to test via the admin routes directly, or create a simple test endpoint.

Actually, let me add a small test endpoint to auth.py that uses require_admin/require_owner, like `/me/admin` and `/me/owner`.

Append to `D:\2026.07.09\AAA\smart-cs\tests\test_auth.py`:

```python
class TestAdminRoleCheck:
    async def _register_and_get_token(self, client, role, test_tenant):
        import uuid
        email = f"{role}-{uuid.uuid4().hex[:6]}@test.com"
        resp = await client.post("/api/v1/auth/register", json={
            "email": email,
            "password": "rolepass1",
            "display_name": f"Role {role}",
            "role": role,
            "tenant_slug": test_tenant.slug,
        })
        return resp.json()["access_token"], email

    async def test_admin_accesses_admin_route(self, client, test_tenant):
        token, _ = await self._register_and_get_token(client, "admin", test_tenant)
        resp = await client.get("/api/v1/auth/me/admin", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp.status_code == 200

    async def test_owner_accesses_admin_route(self, client):
        """owner implicitly passes admin check."""
        # Register owner (creates its own tenant)
        import uuid
        slug = f"owner-test-{uuid.uuid4().hex[:6]}"
        reg = await client.post("/api/v1/auth/register", json={
            "email": f"owner-admin-{uuid.uuid4().hex[:6]}@test.com",
            "password": "ownerpass1",
            "display_name": "Owner Admin",
            "role": "owner",
            "tenant_slug": slug,
            "tenant_name": "Owner Admin Shop",
        })
        token = reg.json()["access_token"]
        resp = await client.get("/api/v1/auth/me/admin", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp.status_code == 200

    async def test_agent_blocked_from_admin_route(self, client, test_tenant):
        token, _ = await self._register_and_get_token(client, "agent", test_tenant)
        resp = await client.get("/api/v1/auth/me/admin", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp.status_code == 403

    async def test_agent_blocked_from_owner_route(self, client, test_tenant):
        token, _ = await self._register_and_get_token(client, "agent", test_tenant)
        resp = await client.get("/api/v1/auth/me/owner", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp.status_code == 403

    async def test_admin_blocked_from_owner_route(self, client, test_tenant):
        token, _ = await self._register_and_get_token(client, "admin", test_tenant)
        resp = await client.get("/api/v1/auth/me/owner", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp.status_code == 403

    async def test_owner_accesses_owner_route(self, client):
        import uuid
        slug = f"owner-only-{uuid.uuid4().hex[:6]}"
        reg = await client.post("/api/v1/auth/register", json={
            "email": f"owner-only-{uuid.uuid4().hex[:6]}@test.com",
            "password": "ownerpass1",
            "display_name": "Owner Only",
            "role": "owner",
            "tenant_slug": slug,
            "tenant_name": "Owner Only Shop",
        })
        token = reg.json()["access_token"]
        resp = await client.get("/api/v1/auth/me/owner", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp.status_code == 200
```

- [ ] **Step 2: 添加 require_admin/require_owner + 测试端点**

In `D:\2026.07.09\AAA\smart-cs\app\api\admin\auth.py`, add after the existing `verify_admin` function:

```python
from app.api.deps import get_current_user, get_db
from app.models.user import User


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("admin", "owner"):
        raise HTTPException(status_code=403, detail="Admin or owner role required")
    return user


def require_owner(user: User = Depends(get_current_user)) -> User:
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Owner role required")
    return user
```

In `D:\2026.07.09\AAA\smart-cs\app\api\auth.py`, add test endpoints for role checks:

```python
from app.api.admin.auth import require_admin, require_owner


@router.get("/me/admin")
def me_admin(user: User = Depends(require_admin)):
    return {"role": user.role, "allowed": True}


@router.get("/me/owner")
def me_owner(user: User = Depends(require_owner)):
    return {"role": user.role, "allowed": True}
```

- [ ] **Step 3: 运行角色检查测试**

```bash
D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/test_auth.py::TestAdminRoleCheck -v --tb=short
```

Expected: 6 passed

- [ ] **Step 4: 验证回归**

```bash
D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/ -v --tb=short 2>&1 | tail -5
```

- [ ] **Step 5: Commit**

```bash
git add app/api/admin/auth.py app/api/auth.py tests/test_auth.py
git commit -m "feat: add require_admin and require_owner role checks

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 9: Admin 路由迁移 — 支持 JWT + API Key 双认证

**Files:**
- Modify: `D:\2026.07.09\AAA\smart-cs\app\api\admin\knowledge.py`
- Modify: `D:\2026.07.09\AAA\smart-cs\app\api\admin\document.py`
- Modify: `D:\2026.07.09\AAA\smart-cs\app\api\admin\analytics.py`

**Interfaces:**
- Consumes: `require_admin`, `verify_admin`

- [ ] **Step 1: 写 admin 路由集成测试**

Append to `D:\2026.07.09\AAA\smart-cs\tests\test_auth.py`:

```python
class TestAdminRouteJWT:
    async def test_knowledge_list_with_jwt(self, client, test_tenant):
        """Admin user can access knowledge list via JWT."""
        import uuid
        email = f"kb-jwt-{uuid.uuid4().hex[:6]}@test.com"
        reg = await client.post("/api/v1/auth/register", json={
            "email": email,
            "password": "kbjwtpass1",
            "display_name": "KB JWT Admin",
            "role": "admin",
            "tenant_slug": test_tenant.slug,
        })
        token = reg.json()["access_token"]

        resp = await client.get(
            f"/api/v1/admin/{test_tenant.slug}/knowledge/",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "items" in resp.json()

    async def test_knowledge_list_with_api_key_still_works(self, admin_client, test_tenant):
        """API key auth still works after JWT migration."""
        resp = await admin_client.get(
            f"/api/v1/admin/{test_tenant.slug}/knowledge/",
        )
        assert resp.status_code == 200
        assert "items" in resp.json()

    async def test_agent_blocked_from_admin_knowledge(self, client, test_tenant):
        """Agent role cannot access admin routes."""
        import uuid
        email = f"agent-block-{uuid.uuid4().hex[:6]}@test.com"
        reg = await client.post("/api/v1/auth/register", json={
            "email": email,
            "password": "agentpass1",
            "display_name": "Agent Blocked",
            "role": "agent",
            "tenant_slug": test_tenant.slug,
        })
        token = reg.json()["access_token"]

        resp = await client.get(
            f"/api/v1/admin/{test_tenant.slug}/knowledge/",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
```

- [ ] **Step 2: 修改 admin 路由 — 双认证支持**

Each admin route currently has: `_admin: AdminApiKey = Depends(verify_admin)`.

For each file (`knowledge.py`, `document.py`, `analytics.py`), make two changes:

**Change 1: Update imports**

Change the import of `verify_admin`:
```python
from app.api.admin.auth import require_admin, verify_admin
```

**Change 2: Update each route signature**

For every route that uses `_admin: AdminApiKey = Depends(verify_admin)`, replace with a dual-auth pattern. Since FastAPI doesn't natively support union dependencies, we use a helper:

In `D:\2026.07.09\AAA\smart-cs\app\api\admin\auth.py`, add:

```python
def require_auth(
    api_key: AdminApiKey = Depends(verify_admin),
) -> AdminApiKey:
    """API Key auth — preserved for backward compatibility."""
    return api_key
```

And then in each admin route, we can accept EITHER a JWT user OR an API key by using two optional parameters and checking at least one:

Actually, a simpler approach: make a single dependency that tries JWT first, then falls back to API Key.

Let me use a cleaner pattern. In `admin/auth.py`, add:

```python
from fastapi import Request as FastAPIRequest


def admin_auth(
    request: FastAPIRequest,
    db: Session = Depends(get_db),
) -> User | AdminApiKey:
    """Authenticate via JWT (Bearer) or API Key (X-Admin-Key)."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        # JWT path
        return get_current_user(request, db)
    # API Key path
    return verify_admin(request, db)
```

But this has a typing issue — returning Union types. The route handlers currently use `_admin: AdminApiKey = Depends(verify_admin)` and access `_admin.tenant_id`. With `User`, they'd use `user.tenant_id` too. Both models have `tenant_id`, so we could use a protocol or just accept `Any`.

Actually, the simplest and cleanest approach is:
1. Keep `verify_admin` as-is for backward compat  
2. For routes that want dual auth, add `admin_auth` that tries JWT first, then API key
3. Return type is `User | AdminApiKey` — both have `.tenant_id`

But wait, the route functions also use `AdminApiKey` type hints. Let me look at the simplest path:

Actually, the **simplest** migration is:
- Just add a NEW dependency `admin_auth` that combines both
- Routes that import it can use either JWT or API Key
- The return type can be a union, or better yet, we create a lightweight dataclass/Protocol

**Simplest viable approach:** Modify the route signature to accept both:

```python
from typing import Union

# In admin/auth.py
async def admin_auth(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Auth via JWT Bearer token — requires admin/owner role."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        user = get_current_user(request, db)
        if user.role not in ("admin", "owner"):
            raise HTTPException(403, detail="Admin or owner role required")
        return user
    # Fallback: try API Key
    api_key = verify_admin(request, db)
    # For API key, we don't have a User — but we can make one up or restructure
    # Actually, we need a cleaner approach...
```

Hmm, this is getting complicated. Let me step back and think about the simplest correct approach.

The cleanest solution: **Keep both auth methods as separate dependencies, and let each route accept either.** 

Since FastAPI can't do union dependencies natively, the simplest practical approach is:

1. Have TWO optional dependencies in each route (one JWT, one API Key)
2. Check at least one is present

But that requires changing every route signature to have two optional params with `Depends()` and then checking... this is messy for 16 routes.

**Much simpler approach:** Make `admin_auth` a single dependency:

```python
def admin_auth(
    request: Request,
    db: Session = Depends(get_db),
) -> tuple[str, str]:  # (tenant_id, auth_method)
    """Authenticate via JWT (Bearer) or API Key (X-Admin-Key).
    Returns (tenant_id, auth_method).
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        credentials = _security(request)
        payload = decode_token(credentials.credentials, expected_type="access")
        user = db.query(User).filter(User.id == payload["sub"]).first()
        if user is None or not user.is_active:
            raise HTTPException(401, detail="Invalid user")
        if user.role not in ("admin", "owner"):
            raise HTTPException(403, detail="Admin or owner role required")
        return (user.tenant_id, "jwt")
    
    # API Key fallback
    api_key = verify_admin(request, db)
    return (api_key.tenant_id, "api_key")
```

Then modify every route: `_admin: AdminApiKey = Depends(verify_admin)` → `_auth: tuple = Depends(admin_auth)` and change `_admin.tenant_id` → `_auth[0]`.

This is a mechanical 16-route change. Let me write it up clearly.

Actually wait, even simpler: just change the dependency and return type, but keep the tenant_id access consistent. Currently all routes use `_admin: AdminApiKey = Depends(verify_admin)` but they don't actually use `_admin` — they use the `tenant` from `get_tenant`. Let me verify...

Looking at the routes:
- knowledge.py line 52: `_admin: AdminApiKey = Depends(verify_admin),` — never referenced in the function body, just there for auth guard
- Actually they DO have `tenant: Tenant = Depends(get_tenant)` which provides the tenant

So the routes don't even use `_admin`! It's purely an auth guard. This makes the migration trivial:

Just change `_admin: AdminApiKey = Depends(verify_admin)` to `_user: User = Depends(require_admin)` and update the import.

For backward compatibility with API keys, we keep `verify_admin` but add `admin_auth` as an optional second dependency... 

OK, the truly simplest approach for Phase 1.2: 
- Admin routes support BOTH auth methods by having two mutually-exclusive optional dependencies
- OR: create a single `admin_auth` that does both

Let me just go with the combined `admin_auth` approach. It's cleanest.

```python
# app/api/admin/auth.py

def admin_auth(
    request: Request,
    db: Session = Depends(get_db),
) -> User | AdminApiKey:
    """Authenticate via JWT (Bearer) or API Key (X-Admin-Key)."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        user = get_current_user(request, db)
        if user.role not in ("admin", "owner"):
            raise HTTPException(403, detail="Admin or owner role required")
        return user
    return verify_admin(request, db)
```

Routes change from:
```python
_admin: AdminApiKey = Depends(verify_admin),
```

To:
```python
_auth = Depends(admin_auth),
```

And since routes don't use `_admin` (they get tenant from `get_tenant`), they don't need to reference `_auth` at all — it's purely a guard.

This is the simplest possible migration. Let me write the plan with this approach.

- [ ] **Step 2: Implement combined admin_auth dependency**

In `D:\2026.07.09\AAA\smart-cs\app\api\admin\auth.py`, add:

```python
from app.api.deps import get_current_user, get_db
from app.models.user import User


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("admin", "owner"):
        raise HTTPException(status_code=403, detail="Admin or owner role required")
    return user


def require_owner(user: User = Depends(get_current_user)) -> User:
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Owner role required")
    return user


def admin_auth(
    request: Request,
    db: Session = Depends(get_db),
):
    """Authenticate via JWT Bearer (admin/owner) or API Key (X-Admin-Key).
    
    Raises 401/403 if neither method succeeds. Returns nothing — purely a guard.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        user = get_current_user(request, db)
        if user.role not in ("admin", "owner"):
            raise HTTPException(status_code=403, detail="Admin or owner role required")
        return
    # Fallback: API Key via X-Admin-Key header
    verify_admin(request, db)
```

Note: This requires importing `Request` from fastapi (already imported at top of admin/auth.py).

- [ ] **Step 3: Update each admin route**

For all 16 routes across 3 files, change:
```python
_admin: AdminApiKey = Depends(verify_admin),
```
To:
```python
_auth = Depends(admin_auth),
```

And update imports in each file: change `from app.api.admin.auth import verify_admin` to `from app.api.admin.auth import admin_auth`.

Also remove unused `AdminApiKey` import from the admin route files (since they no longer reference it directly).

Run search-and-replace:

In `D:\2026.07.09\AAA\smart-cs\app\api\admin\knowledge.py`:
- Line 10: `from app.api.admin.auth import verify_admin` → `from app.api.admin.auth import admin_auth`
- Line 14: Remove `AdminApiKey, ` from import (leaving `from app.models.tenant import Tenant`)
- All 8 instances of `_admin: AdminApiKey = Depends(verify_admin),` → `_auth = Depends(admin_auth),`

In `D:\2026.07.09\AAA\smart-cs\app\api\admin\document.py`:
- Line 10: `from app.api.admin.auth import verify_admin` → `from app.api.admin.auth import admin_auth`
- Line 12: Remove `AdminApiKey, ` from import
- All 4 instances of `_admin: AdminApiKey = Depends(verify_admin),` → `_auth = Depends(admin_auth),`

In `D:\2026.07.09\AAA\smart-cs\app\api\admin\analytics.py`:
- Line 13: `from app.api.admin.auth import verify_admin` → `from app.api.admin.auth import admin_auth`
- Line 15: Remove `AdminApiKey, ` from import
- All 4 instances of `_admin: AdminApiKey = Depends(verify_admin),` → `_auth = Depends(admin_auth),`

- [ ] **Step 4: 运行 admin 路由 JWT 测试**

```bash
D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/test_auth.py::TestAdminRouteJWT -v --tb=short
```

Expected: 3 passed

- [ ] **Step 5: 验证回归 — 包括所有现有 API Key 测试**

```bash
D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/ -v --tb=short 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
git add app/api/admin/auth.py app/api/admin/knowledge.py app/api/admin/document.py app/api/admin/analytics.py tests/test_auth.py
git commit -m "feat: migrate admin routes to dual JWT + API Key auth

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 10: 最终验证 + 清理

**Files:**
- Verify: all tests pass
- Verify: manual smoke test

- [ ] **Step 1: 运行完整测试套件**

```bash
D:/2026.07.09/conda-envs/smart-cs/python.exe -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: all tests pass (94 existing + all new auth tests)

- [ ] **Step 2: 验证应用启动**

```bash
timeout 5 D:/2026.07.09/conda-envs/smart-cs/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 2>&1 || true
```

Expected: No import errors, app starts successfully.

- [ ] **Step 3: 最终 Commit（如有残留改动）**

```bash
git status
git add -A
git commit -m "chore: final cleanup for Phase 1.2 JWT auth

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---
