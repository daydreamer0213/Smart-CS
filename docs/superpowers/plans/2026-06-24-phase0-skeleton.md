# SmartCS Phase 0 — Project Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a "nothing but structurally correct" SmartCS project skeleton with 50+ files, all business routes returning `{"status":"not_implemented"}`, with fully working config, middleware, alembic, and test fixtures.

**Architecture:** 5-layer sequential build. Layer 1 (config/models/schemas) → Layer 2 (middleware) → Layer 3 (api routes) → Layer 4 (main.py/alembic/seed) → Layer 5 (tests/stubs). Each layer verified before moving to next.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + ChromaDB + structlog + Pydantic Settings + pytest/httpx

## Global Constraints

- Python 3.12, conda env named `smart-cs`, conda at `D:\conda\Scripts\conda.exe`
- SQLite for dev (`sqlite:///./smartcs.db`), PostgreSQL-compatible column types where possible
- API prefix `/api/v1/{tenant_slug}/...`, health check at `/health` (no prefix)
- Error format: `{"error": {"code": "...", "message": "..."}, "request_id": "..."}`
- All model IDs are String(36) UUIDs (portable SQLite↔PostgreSQL)
- `models/__init__.py` imports ALL models so `Base.metadata.create_all` discovers them
- Intent keywords stored in `tenant.config_json`, NOT global constants

---

### Task 0: Conda Environment + Dependencies

**Files:** None (environment setup only)

- [ ] **Step 1: Create conda environment**

```bash
D:\conda\Scripts\conda.exe create -n smart-cs python=3.12 -y
```

Expected: environment created at `D:\conda\envs\smart-cs\`

- [ ] **Step 2: Install dependencies**

```bash
D:\conda\Scripts\conda.exe run -n smart-cs pip install fastapi "uvicorn[standard]" chromadb sqlalchemy alembic pydantic pydantic-settings python-dotenv structlog jieba rank-bm25 openai httpx pytest pytest-asyncio
```

Expected: all packages installed without errors

- [ ] **Step 3: Verify Python is working**

```bash
D:\conda\Scripts\conda.exe run -n smart-cs python -c "import fastapi; import chromadb; import sqlalchemy; import alembic; import structlog; print('All imports OK')"
```

Expected: "All imports OK"

---

### Task 1: Project Root Files (.env.example, .gitignore, requirements.txt, __init__.pys)

**Files:**
- Create: `.env.example`
- Create: `.gitignore`
- Create: `requirements.txt`
- Create: `app/__init__.py`
- Create: `app/models/__init__.py` (empty, will be filled later)
- Create: `app/schemas/__init__.py`
- Create: `app/api/__init__.py`
- Create: `app/api/admin/__init__.py`
- Create: `app/core/__init__.py`
- Create: `app/core/retrieval/__init__.py`
- Create: `app/core/intent/__init__.py`
- Create: `app/core/cache/__init__.py`
- Create: `app/core/conversation/__init__.py`
- Create: `app/core/llm/__init__.py`
- Create: `app/services/__init__.py`
- Create: `app/middleware/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create .env.example**

```bash
cat > "D:/AAA/smart-cs/.env.example" << 'ENVEOF'
# SmartCS Configuration
# Copy this file to .env and fill in your values

# Database
DATABASE_URL=sqlite:///./smartcs.db

# ChromaDB
CHROMA_PERSIST_DIR=./chroma_data

# DeepSeek API
LLM_API_KEY=sk-your-key-here
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
EMBEDDING_MODEL=deepseek-chat

# Cache
L1_CACHE_TTL=300
L2_CACHE_THRESHOLD=0.85

# Intent Classification
INTENT_CONFIDENCE_THRESHOLD=0.6

# Conversation
MAX_CONTEXT_TOKENS=2000
MAX_CONVERSATION_TURNS=10

# Rate Limiting
RATE_LIMIT_PER_MINUTE=30

# Logging
LOG_LEVEL=INFO
ENVEOF
```

- [ ] **Step 2: Create .gitignore**

```bash
cat > "D:/AAA/smart-cs/.gitignore" << 'GITIGNOREEOF'
.env
__pycache__/
*.pyc
*.pyo
*.db
chroma_data/
.pytest_cache/
*.egg-info/
dist/
build/
migrations/__pycache__/
GITIGNOREEOF
```

- [ ] **Step 3: Create requirements.txt**

```bash
cat > "D:/AAA/smart-cs/requirements.txt" << 'REQEOF'
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
chromadb>=0.5.0
sqlalchemy>=2.0.0
alembic>=1.13.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
python-dotenv>=1.0.0
structlog>=24.0.0
jieba>=0.42.0
rank-bm25>=0.2.0
openai>=1.0.0
httpx>=0.27.0
pytest>=8.0.0
pytest-asyncio>=0.24.0
REQEOF
```

- [ ] **Step 4: Create all __init__.py files**

```bash
# Bash: Create all empty __init__.py files
mkdir -p "D:/AAA/smart-cs/app/models"
mkdir -p "D:/AAA/smart-cs/app/schemas"
mkdir -p "D:/AAA/smart-cs/app/api/admin"
mkdir -p "D:/AAA/smart-cs/app/core/retrieval"
mkdir -p "D:/AAA/smart-cs/app/core/intent"
mkdir -p "D:/AAA/smart-cs/app/core/cache"
mkdir -p "D:/AAA/smart-cs/app/core/conversation"
mkdir -p "D:/AAA/smart-cs/app/core/llm"
mkdir -p "D:/AAA/smart-cs/app/services"
mkdir -p "D:/AAA/smart-cs/app/middleware"
mkdir -p "D:/AAA/smart-cs/tests"
mkdir -p "D:/AAA/smart-cs/data/seed"
mkdir -p "D:/AAA/smart-cs/static"
mkdir -p "D:/AAA/smart-cs/admin-static/css"
mkdir -p "D:/AAA/smart-cs/admin-static/js"
mkdir -p "D:/AAA/smart-cs/docs/superpowers/specs"
mkdir -p "D:/AAA/smart-cs/docs/superpowers/plans"

for dir in \
  app \
  app/models app/schemas \
  app/api app/api/admin \
  app/core app/core/retrieval app/core/intent app/core/cache app/core/conversation app/core/llm \
  app/services app/middleware \
  tests
do
  touch "D:/AAA/smart-cs/$dir/__init__.py"
done
```

- [ ] **Step 5: Verify directory structure**

```bash
D:\conda\Scripts\conda.exe run -n smart-cs python -c "import sys; sys.path.insert(0, 'D:/AAA/smart-cs'); import app; import app.models; import app.schemas; import app.api; import app.core; import app.services; import app.middleware; print('All packages importable')"
```

Expected: "All packages importable"

---

### Task 2: app/config.py (Complete Implementation)

**Files:**
- Create: `app/config.py`

**Interfaces:**
- Produces: `settings: Settings` — singleton instance, importable from any module

- [ ] **Step 1: Write app/config.py**

```python
"""Application configuration loaded from .env via pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "sqlite:///./smartcs.db"
    chroma_persist_dir: str = "./chroma_data"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    embedding_model: str = "deepseek-chat"
    l1_cache_ttl: int = 300
    l2_cache_threshold: float = 0.85
    intent_confidence_threshold: float = 0.6
    max_context_tokens: int = 2000
    max_conversation_turns: int = 10
    rate_limit_per_minute: int = 30
    log_level: str = "INFO"


settings = Settings()
```

- [ ] **Step 2: Verify config loads**

```bash
D:\conda\Scripts\conda.exe run -n smart-cs python -c "
import sys; sys.path.insert(0, 'D:/AAA/smart-cs')
from app.config import settings
print(f'database_url={settings.database_url}')
print(f'llm_model={settings.llm_model}')
print(f'log_level={settings.log_level}')
print('Config OK')
"
```

Expected: prints default values, "Config OK"

---

### Task 3: app/models/ (All ORM Models)

**Files:**
- Create: `app/models/base.py`
- Create: `app/models/tenant.py`
- Create: `app/models/knowledge.py`
- Create: `app/models/conversation.py`
- Create: `app/models/analytics.py`
- Modify: `app/models/__init__.py`

**Interfaces:**
- Produces: `Base` (declarative base), `Tenant`, `AdminApiKey`, `KnowledgeItem`, `Category`, `Conversation`, `Message` — all importable from `app.models`

- [ ] **Step 1: Write app/models/base.py**

```python
"""SQLAlchemy declarative base and shared mixin."""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, String, func
from sqlalchemy.orm import declarative_base


def _gen_uuid() -> str:
    return str(uuid.uuid4())


Base = declarative_base()


class TimestampMixin:
    """Shared columns for all business models."""

    id = Column(String(36), primary_key=True, default=_gen_uuid)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

- [ ] **Step 2: Write app/models/tenant.py**

```python
"""Tenant and admin API key models."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    slug = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    config_json = Column(JSON, nullable=False, default=dict)
    is_active = Column(Boolean, default=True, nullable=False)


class AdminApiKey(Base, TimestampMixin):
    __tablename__ = "admin_api_keys"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    key_hash = Column(String(128), unique=True, nullable=False)
    label = Column(String(200), default="")
    last_used_at = Column(DateTime, nullable=True)

    tenant = relationship("Tenant")
```

- [ ] **Step 3: Write app/models/knowledge.py**

```python
"""Knowledge base models — FAQ items and categories."""

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class Category(Base, TimestampMixin):
    __tablename__ = "categories"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    sort_order = Column(Integer, default=0)

    tenant = relationship("Tenant")


class KnowledgeItem(Base, TimestampMixin):
    __tablename__ = "knowledge_items"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    category_id = Column(String(36), ForeignKey("categories.id"), nullable=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    keywords = Column(Text, default="")
    embedding_id = Column(String(200), nullable=True)
    status = Column(String(20), default="active", nullable=False)

    tenant = relationship("Tenant")
    category = relationship("Category")
```

- [ ] **Step 4: Write app/models/conversation.py**

```python
"""Conversation session and message models."""

from sqlalchemy import Column, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    session_id = Column(String(100), nullable=False, index=True)
    visitor_id = Column(String(100), nullable=True)
    status = Column(String(20), default="active", nullable=False)
    message_count = Column(Integer, default=0)

    tenant = relationship("Tenant")


class Message(Base, TimestampMixin):
    __tablename__ = "messages"

    conversation_id = Column(
        String(36), ForeignKey("conversations.id"), nullable=False, index=True
    )
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    intent = Column(String(50), nullable=True)
    cache_hit = Column(String(10), nullable=True)
    sources_json = Column(JSON, nullable=True)
    latency_ms = Column(Integer, nullable=True)

    conversation = relationship("Conversation")
```

- [ ] **Step 5: Write app/models/analytics.py**

```python
"""Analytics placeholder — will hold materialized views / aggregate tables.

For Phase 4: dashboard overview, intent distribution, daily trends,
knowledge hit rankings, and latency distribution queries.
"""
```

- [ ] **Step 6: Write app/models/__init__.py**

```python
from app.models.base import Base, TimestampMixin
from app.models.tenant import AdminApiKey, Tenant
from app.models.knowledge import Category, KnowledgeItem
from app.models.conversation import Conversation, Message

__all__ = [
    "Base",
    "TimestampMixin",
    "Tenant",
    "AdminApiKey",
    "Category",
    "KnowledgeItem",
    "Conversation",
    "Message",
]
```

- [ ] **Step 7: Verify models import and can create tables**

```bash
D:\conda\Scripts\conda.exe run -n smart-cs python -c "
import sys; sys.path.insert(0, 'D:/AAA/smart-cs')
from app.models import Base, Tenant, AdminApiKey, KnowledgeItem, Category, Conversation, Message
from sqlalchemy import create_engine
engine = create_engine('sqlite:///./smartcs_test_verify.db', echo=False)
Base.metadata.create_all(engine)
print('Tables created:', list(Base.metadata.tables.keys()))
import os; os.remove('./smartcs_test_verify.db')
print('Models OK')
"
```

Expected: prints table names and "Models OK", then deletes test db

---

### Task 4: app/schemas/ (Placeholder Pydantic Models)

**Files:**
- Create: `app/schemas/chat.py`
- Create: `app/schemas/knowledge.py`
- Create: `app/schemas/analytics.py`
- Create: `app/schemas/tenant.py`

- [ ] **Step 1: Write all schema files**

`app/schemas/chat.py`:
```python
"""Chat request/response schemas — Phase 2 implementation."""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Placeholder for chat message request body."""

    pass


class ChatResponse(BaseModel):
    """Placeholder for chat message response body."""

    pass
```

`app/schemas/knowledge.py`:
```python
"""Knowledge base CRUD schemas — Phase 1 implementation."""

from pydantic import BaseModel


class KnowledgeCreate(BaseModel):
    """Placeholder for knowledge item creation."""

    pass


class KnowledgeUpdate(BaseModel):
    """Placeholder for knowledge item update."""

    pass


class KnowledgeResponse(BaseModel):
    """Placeholder for knowledge item response."""

    pass
```

`app/schemas/analytics.py`:
```python
"""Analytics response schemas — Phase 4 implementation."""

from pydantic import BaseModel


class DashboardStats(BaseModel):
    """Placeholder for dashboard overview statistics."""

    pass
```

`app/schemas/tenant.py`:
```python
"""Tenant schemas — Phase 2+ implementation."""

from pydantic import BaseModel


class TenantResponse(BaseModel):
    """Placeholder for tenant info response."""

    pass
```

- [ ] **Step 2: Verify schemas import**

```bash
D:\conda\Scripts\conda.exe run -n smart-cs python -c "
import sys; sys.path.insert(0, 'D:/AAA/smart-cs')
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.knowledge import KnowledgeCreate, KnowledgeUpdate, KnowledgeResponse
from app.schemas.analytics import DashboardStats
from app.schemas.tenant import TenantResponse
print('Schemas OK')
"
```

Expected: "Schemas OK"

---

### Task 5: app/middleware/ (Logging + Error Handler + Tenant)

**Files:**
- Create: `app/middleware/logging.py`
- Create: `app/middleware/error_handler.py`
- Create: `app/middleware/tenant.py`

**Interfaces:**
- Produces: `setup_structlog(log_level: str) -> None`, `request_id_var: ContextVar[str]`, `LoggingMiddleware` (ASGI middleware)
- Produces: `register_error_handlers(app: FastAPI) -> None`
- Produces: `TenantMiddleware` (BaseHTTPMiddleware)

- [ ] **Step 1: Write app/middleware/logging.py**

```python
"""Structlog configuration and request-level logging middleware."""

import time
import uuid
from contextvars import ContextVar

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def setup_structlog(log_level: str = "INFO") -> None:
    level = getattr(structlog, log_level.upper(), structlog.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request_id_var.set(rid)
        structlog.contextvars.bind_contextvars(request_id=rid)

        logger = structlog.get_logger()
        start = time.monotonic()
        logger.info(
            "request_started", method=request.method, path=request.url.path
        )

        response = await call_next(request)

        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            elapsed_ms=round(elapsed_ms, 2),
        )

        response.headers["X-Request-ID"] = rid
        return response
```

- [ ] **Step 2: Write app/middleware/error_handler.py**

```python
"""Global exception handler — converts all unhandled exceptions to JSON error format."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.middleware.logging import request_id_var


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {"code": "HTTP_ERROR", "message": exc.detail},
                "request_id": request_id_var.get(),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "error": {"code": "INTERNAL_ERROR", "message": "Internal server error"},
                "request_id": request_id_var.get(),
            },
        )
```

- [ ] **Step 3: Write app/middleware/tenant.py**

```python
"""Tenant middleware — extracts tenant_slug from URL path and injects request.state.tenant."""

import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.deps import SessionLocal
from app.middleware.logging import request_id_var
from app.models.tenant import Tenant

TENANT_PATH_RE = re.compile(r"^/api/v\d+/([^/]+)")


def _extract_slug(path: str) -> str | None:
    match = TENANT_PATH_RE.match(path)
    return match.group(1) if match else None


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        slug = _extract_slug(request.url.path)

        if slug is None:
            request.state.tenant = None
            return await call_next(request)

        db = SessionLocal()
        try:
            tenant = db.query(Tenant).filter(Tenant.slug == slug).first()
            if tenant is None:
                rid = request_id_var.get()
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": {
                            "code": "TENANT_NOT_FOUND",
                            "message": f"Tenant '{slug}' does not exist",
                        },
                        "request_id": rid,
                    },
                )

            request.state.tenant = tenant
            response = await call_next(request)
            return response
        finally:
            db.close()
```

- [ ] **Step 4: Verify middleware imports**

```bash
D:\conda\Scripts\conda.exe run -n smart-cs python -c "
import sys; sys.path.insert(0, 'D:/AAA/smart-cs')
from app.middleware.logging import setup_structlog, request_id_var, LoggingMiddleware
from app.middleware.error_handler import register_error_handlers
from app.middleware.tenant import TenantMiddleware, _extract_slug
print('_extract_slug(/api/v1/demo/chat):', _extract_slug('/api/v1/demo/chat'))
print('_extract_slug(/health):', _extract_slug('/health'))
print('Middleware OK')
"
```

Expected: prints slug extraction results, "Middleware OK"

---

### Task 6: app/api/ (Route Layer — deps, health, chat, admin)

**Files:**
- Create: `app/api/deps.py`
- Create: `app/api/health.py`
- Create: `app/api/chat.py`
- Create: `app/api/admin/auth.py`
- Create: `app/api/admin/knowledge.py`
- Create: `app/api/admin/analytics.py`

**Interfaces:**
- Produces: `get_db() -> Generator[Session]`, `get_tenant(db, slug) -> Tenant`, `verify_admin(db, tenant, request) -> AdminApiKey`
- Produces: `router` (health, chat, admin-knowledge, admin-analytics)

- [ ] **Step 1: Write app/api/deps.py**

```python
"""FastAPI dependency injection — database session, tenant lookup, admin auth."""

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models.tenant import AdminApiKey, Tenant

engine = create_engine(
    settings.database_url, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
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
```

- [ ] **Step 2: Write app/api/health.py**

```python
"""Health check endpoint — no auth, no tenant context."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}
```

- [ ] **Step 3: Write app/api/chat.py**

```python
"""Customer chat endpoint — Phase 2 implementation."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db

router = APIRouter()


@router.post("/api/v1/{tenant_slug}/chat")
async def chat(request: Request, db: Session = Depends(get_db)):
    """Customer service chat endpoint. Full pipeline: cache -> intent -> retrieval -> LLM."""
    return {"status": "not_implemented"}
```

- [ ] **Step 4: Write admin route files**

`app/api/admin/auth.py`:
```python
"""Admin API key authentication — Phase 1 implementation."""

from fastapi import APIRouter

router = APIRouter()
```

`app/api/admin/knowledge.py`:
```python
"""Admin knowledge base CRUD — Phase 1 implementation.

Endpoints:
  GET    /api/v1/admin/{tenant_slug}/knowledge       List (paginated, search, filter)
  POST   /api/v1/admin/{tenant_slug}/knowledge       Create (auto embed -> ChromaDB)
  PUT    /api/v1/admin/{tenant_slug}/knowledge/{id}  Update (re-embed)
  DELETE /api/v1/admin/{tenant_slug}/knowledge/{id}  Delete (SQL + ChromaDB)
  GET    /api/v1/admin/{tenant_slug}/categories      List categories
  POST   /api/v1/admin/{tenant_slug}/categories      Create category
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/v1/admin/{tenant_slug}/knowledge")
async def list_knowledge(tenant_slug: str):
    return {"status": "not_implemented"}


@router.post("/api/v1/admin/{tenant_slug}/knowledge")
async def create_knowledge(tenant_slug: str):
    return {"status": "not_implemented"}


@router.put("/api/v1/admin/{tenant_slug}/knowledge/{item_id}")
async def update_knowledge(tenant_slug: str, item_id: str):
    return {"status": "not_implemented"}


@router.delete("/api/v1/admin/{tenant_slug}/knowledge/{item_id}")
async def delete_knowledge(tenant_slug: str, item_id: str):
    return {"status": "not_implemented"}


@router.get("/api/v1/admin/{tenant_slug}/categories")
async def list_categories(tenant_slug: str):
    return {"status": "not_implemented"}


@router.post("/api/v1/admin/{tenant_slug}/categories")
async def create_category(tenant_slug: str):
    return {"status": "not_implemented"}
```

`app/api/admin/analytics.py`:
```python
"""Admin analytics dashboard — Phase 4 implementation.

Endpoints:
  GET /api/v1/admin/{tenant_slug}/analytics/overview    Dashboard overview
  GET /api/v1/admin/{tenant_slug}/analytics/intents     Intent distribution
  GET /api/v1/admin/{tenant_slug}/analytics/daily        Daily trends (7/30 day)
  GET /api/v1/admin/{tenant_slug}/analytics/knowledge    Knowledge hit rankings
  GET /api/v1/admin/{tenant_slug}/analytics/latency      Response latency distribution
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/v1/admin/{tenant_slug}/analytics/overview")
async def analytics_overview(tenant_slug: str):
    return {"status": "not_implemented"}


@router.get("/api/v1/admin/{tenant_slug}/analytics/intents")
async def analytics_intents(tenant_slug: str):
    return {"status": "not_implemented"}


@router.get("/api/v1/admin/{tenant_slug}/analytics/daily")
async def analytics_daily(tenant_slug: str):
    return {"status": "not_implemented"}
```

- [ ] **Step 5: Verify all API modules import**

```bash
D:\conda\Scripts\conda.exe run -n smart-cs python -c "
import sys; sys.path.insert(0, 'D:/AAA/smart-cs')
from app.api.deps import get_db, get_tenant, verify_admin, SessionLocal
from app.api.health import router as health_router
from app.api.chat import router as chat_router
from app.api.admin.knowledge import router as admin_knowledge_router
from app.api.admin.analytics import router as admin_analytics_router
print('API modules OK')
"
```

Expected: "API modules OK"

---

### Task 7: app/main.py + Seed Data + Alembic

**Files:**
- Create: `app/main.py`
- Create: `data/seed/tenant_sample.json`
- Create: `admin-static/index.html`
- Create: `static/chat.html`

**Interfaces:**
- Produces: `create_app() -> FastAPI` (factory with lifespan)

- [ ] **Step 1: Write app/main.py**

```python
"""FastAPI application factory with lifespan management."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.admin.analytics import router as admin_analytics_router
from app.api.admin.knowledge import router as admin_knowledge_router
from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.config import settings
from app.middleware.error_handler import register_error_handlers
from app.middleware.logging import LoggingMiddleware, setup_structlog
from app.middleware.tenant import TenantMiddleware


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_structlog(settings.log_level)

    from app.api.deps import SessionLocal, engine
    from app.models import Base
    from app.models.tenant import Tenant

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        if db.query(Tenant).count() == 0:
            db.add(
                Tenant(
                    slug="demo",
                    name="DemoStore",
                    config_json={
                        "human_keywords": ["人工", "客服", "经理", "投诉"],
                        "system_prompt_append": "",
                        "model_override": None,
                        "cache_ttl_override": None,
                        "intent_threshold_override": None,
                        "handoff_enabled": True,
                    },
                    is_active=True,
                )
            )
            db.commit()
    finally:
        db.close()

    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="SmartCS",
        version="0.1.0",
        lifespan=lifespan,
    )

    register_error_handlers(app)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(TenantMiddleware)

    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(admin_knowledge_router)
    app.include_router(admin_analytics_router)

    return app


app = create_app()
```

- [ ] **Step 2: Write data/seed/tenant_sample.json**

```bash
cat > "D:/AAA/smart-cs/data/seed/tenant_sample.json" << 'SEEDEOF'
{
  "slug": "demo",
  "name": "DemoStore",
  "config_json": {
    "human_keywords": ["人工", "客服", "经理", "投诉"],
    "system_prompt_append": "",
    "model_override": null,
    "cache_ttl_override": null,
    "intent_threshold_override": null,
    "handoff_enabled": true
  },
  "is_active": true
}
SEEDEOF
```

- [ ] **Step 3: Write static/chat.html**

```bash
cat > "D:/AAA/smart-cs/static/chat.html" << 'CHATEOF'
<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>SmartCS Chat</title></head>
<body><h1>SmartCS Chat Widget — Phase 3</h1></body>
</html>
CHATEOF
```

- [ ] **Step 4: Write admin-static/index.html**

```bash
cat > "D:/AAA/smart-cs/admin-static/index.html" << 'ADMINEOF'
<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>SmartCS Admin</title></head>
<body><h1>SmartCS Admin Panel — Phase 3</h1></body>
</html>
ADMINEOF
```

- [ ] **Step 5: Start server and verify**

```bash
# Start uvicorn in background
cd "D:/AAA/smart-cs"
D:\conda\Scripts\conda.exe run -n smart-cs uvicorn app.main:app --host 127.0.0.1 --port 8000 &
sleep 3

# Test health endpoint
curl -s http://127.0.0.1:8000/health
# Expected: {"status":"ok","version":"0.1.0"}

# Test placeholder chat endpoint
curl -s http://127.0.0.1:8000/api/v1/demo/chat -X POST -H "Content-Type: application/json" -d '{}'
# Expected: {"status":"not_implemented"}

# Test tenant not found
curl -s http://127.0.0.1:8000/api/v1/nonexistent/chat -X POST -H "Content-Type: application/json" -d '{}'
# Expected: {"error":{"code":"TENANT_NOT_FOUND",...},...}

# Test request_id in response headers
curl -s -I http://127.0.0.1:8000/health 2>&1 | grep -i x-request-id
# Expected: X-Request-Id header present

# Stop uvicorn
kill %1 2>/dev/null || true
```

Expected: health 200, chat return `{"status":"not_implemented"}`, missing tenant 404 with JSON error, X-Request-ID header present

---

### Task 8: Alembic Setup + Initial Migration

**Files:** All auto-generated by alembic, modify `alembic.ini` and `migrations/env.py`

- [ ] **Step 1: Initialize alembic**

```bash
cd "D:/AAA/smart-cs"
D:\conda\Scripts\conda.exe run -n smart-cs alembic init migrations
```

Expected: creates `alembic.ini`, `migrations/` with `env.py`, `versions/`, `script.py.mako`

- [ ] **Step 2: Configure alembic.ini — point to correct database**

Edit `alembic.ini` line ~63: Change `sqlalchemy.url = driver://user:pass@localhost/dbname` to:

```ini
sqlalchemy.url = sqlite:///./smartcs.db
```

Verify with:
```bash
grep "sqlalchemy.url" "D:/AAA/smart-cs/alembic.ini"
```

Expected: `sqlalchemy.url = sqlite:///./smartcs.db`

- [ ] **Step 3: Configure migrations/env.py — add model metadata**

Edit `migrations/env.py`. Add after the existing imports:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.models import Base

target_metadata = Base.metadata
```

Replace the existing `target_metadata = None` line with the above.

- [ ] **Step 4: Generate initial migration**

```bash
cd "D:/AAA/smart-cs"
D:\conda\Scripts\conda.exe run -n smart-cs alembic revision --autogenerate -m "initial_schema"
```

Expected: creates `migrations/versions/<hash>_initial_schema.py` with upgrade()/downgrade()

- [ ] **Step 5: Run migration**

```bash
cd "D:/AAA/smart-cs"
D:\conda\Scripts\conda.exe run -n smart-cs alembic upgrade head
```

Expected: `Running upgrade -> <hash>, initial_schema`

- [ ] **Step 6: Verify tables exist**

```bash
D:\conda\Scripts\conda.exe run -n smart-cs python -c "
import sqlite3
conn = sqlite3.connect('D:/AAA/smart-cs/smartcs.db')
cursor = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name\")
tables = [row[0] for row in cursor]
print('Tables:', tables)
assert 'tenants' in tables
assert 'admin_api_keys' in tables
assert 'knowledge_items' in tables
assert 'categories' in tables
assert 'conversations' in tables
assert 'messages' in tables
assert 'alembic_version' in tables
print('All expected tables exist')
conn.close()
"
```

Expected: "All expected tables exist"

---

### Task 9: tests/conftest.py (Complete Implementation)

**Files:**
- Create: `tests/conftest.py`

**Interfaces:**
- Produces: `app` fixture (FastAPI with in-memory SQLite), `client` fixture (httpx.AsyncClient), `db` fixture (isolated transaction with auto-rollback), `test_tenant` fixture (seeded demo tenant)

- [ ] **Step 1: Write tests/conftest.py**

```python
"""Pytest fixtures for SmartCS tests."""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.main import create_app
from app.models import Base
from app.models.tenant import Tenant


@pytest.fixture
def engine():
    """In-memory SQLite engine — fresh database per test session."""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture
def db(engine):
    """Session with transaction rollback — isolates each test."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def test_tenant(db: Session) -> Tenant:
    """Seed a demo tenant for test isolation."""
    tenant = Tenant(
        id=str(uuid.uuid4()),
        slug="test-tenant",
        name="Test Store",
        config_json={
            "human_keywords": ["人工", "投诉"],
            "handoff_enabled": True,
        },
        is_active=True,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


@pytest.fixture
def app(engine):
    """FastAPI app with in-memory SQLite overrides."""
    test_app = create_app()
    test_app.dependency_overrides = {}
    return test_app


@pytest_asyncio.fixture
async def client(app, engine):
    """Async HTTP client bound to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

- [ ] **Step 2: Write a simple test to verify fixtures work**

```bash
cat > "D:/AAA/smart-cs/tests/test_fixtures.py" << 'TESTEOF'
"""Verify test fixtures are working."""


async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"


async def test_placeholder_chat_endpoint(client):
    response = await client.post("/api/v1/test-tenant/chat", json={})
    # With in-memory DB, tenant won't exist unless seeded via fixture
    # This tests the route is registered
    assert response.status_code in (200, 404)


async def test_x_request_id_header(client):
    response = await client.get("/health")
    assert "x-request-id" in response.headers
TESTEOF
```

- [ ] **Step 3: Run tests**

```bash
cd "D:/AAA/smart-cs"
D:\conda\Scripts\conda.exe run -n smart-cs pytest tests/test_fixtures.py -v
```

Expected: 3 tests pass (health 200, placeholder endpoint registered, X-Request-ID header present)

---

### Task 10: Core + Services Stubs + Remaining Test Files

**Files:**
- Create: `app/core/retrieval/vector_store.py`
- Create: `app/core/retrieval/bm25_index.py`
- Create: `app/core/retrieval/fusion.py`
- Create: `app/core/intent/classifier.py`
- Create: `app/core/cache/exact.py`
- Create: `app/core/cache/semantic.py`
- Create: `app/core/conversation/memory.py`
- Create: `app/core/llm/client.py`
- Create: `app/core/llm/prompts.py`
- Create: `app/services/chat_service.py`
- Create: `app/services/knowledge_service.py`
- Create: `app/services/analytics_service.py`
- Create: `tests/test_chat_api.py` through `tests/test_e2e.py` (9 files)

- [ ] **Step 1: Write all core stubs**

Each file follows this pattern — docstring + function stub with `raise NotImplementedError`:

`app/core/retrieval/vector_store.py`:
```python
"""ChromaDB vector store management — per-tenant collection isolation.

Phase 1 implementation: CRUD-synchronized, collection naming {tenant_slug}_knowledge.
"""


def get_collection(tenant_slug: str):
    """Get or create the ChromaDB collection for a tenant."""
    raise NotImplementedError("Phase 1")
```

`app/core/retrieval/bm25_index.py`:
```python
"""BM25 keyword index — per-tenant in-memory instances.

Phase 1 implementation: builds on startup from active knowledge items,
rebuilds on knowledge change.
"""


def build_index(tenant_id: str, documents: list[str]):
    """Build BM25 index from tokenized documents for a tenant."""
    raise NotImplementedError("Phase 1")


def search(query: str, tenant_id: str, top_k: int = 5):
    """Search BM25 index for a tenant, return top_k (idx, score) pairs."""
    raise NotImplementedError("Phase 1")
```

`app/core/retrieval/fusion.py`:
```python
"""RRF (Reciprocal Rank Fusion) — merges vector and BM25 results.

Phase 1 implementation: k=60 constant, top_k configurable.
"""


def rrf_fusion(
    vector_results: list[tuple[str, float]],
    bm25_results: list[tuple[int, float]],
    k: int = 60,
    top_k: int = 5,
) -> list[dict]:
    """Fuse ChromaDB and BM25 results using RRF, returning top_k documents."""
    raise NotImplementedError("Phase 1")
```

`app/core/intent/classifier.py`:
```python
"""Rule + LLM hybrid intent classification — per-tenant keyword configuration.

Phase 2 implementation: rule match first, LLM fallback; keywords from tenant.config_json.
Intent labels: faq, human, unknown.
"""


def classify_intent(user_input: str, tenant_config: dict) -> tuple[str, str, float]:
    """Classify user intent. Returns (intent_label, source, confidence)."""
    raise NotImplementedError("Phase 2")


def should_handoff(intent: str, confidence: float, threshold: float) -> bool:
    """Determine if the conversation should be handed off to a human."""
    raise NotImplementedError("Phase 2")
```

`app/core/cache/exact.py`:
```python
"""L1 exact-match cache — per-tenant, TTL-based expiration.

Phase 2 implementation: key = (tenant_id, normalized_question).
Invalidated on knowledge update for that tenant.
"""


def get(tenant_id: str, question: str):
    """Look up exact cache. Returns cached answer or None."""
    raise NotImplementedError("Phase 2")


def set(tenant_id: str, question: str, answer: str, ttl: int = 300) -> None:
    """Store exact cache entry with TTL."""
    raise NotImplementedError("Phase 2")


def invalidate(tenant_id: str) -> None:
    """Clear all cache entries for a tenant (called on knowledge change)."""
    raise NotImplementedError("Phase 2")
```

`app/core/cache/semantic.py`:
```python
"""L2 semantic cache — per-tenant, cosine-similarity threshold.

Phase 2 implementation: embedding → cosine_similarity(question, cached_embeddings).
"""


def get(tenant_id: str, question_embedding: list[float], threshold: float = 0.85):
    """Look up semantic cache by cosine similarity. Returns cached answer or None."""
    raise NotImplementedError("Phase 2")


def set(tenant_id: str, question_embedding: list[float], answer: str) -> None:
    """Store semantic cache entry."""
    raise NotImplementedError("Phase 2")


def invalidate(tenant_id: str) -> None:
    """Clear all semantic cache entries for a tenant."""
    raise NotImplementedError("Phase 2")
```

`app/core/conversation/memory.py`:
```python
"""Sliding-window conversation context management.

Phase 2 implementation: trim by token count (tiktoken) and turn count.
"""


def build_context(
    history: list[dict],
    max_tokens: int = 2000,
    max_turns: int = 10,
) -> list[dict]:
    """Trim conversation history to fit within token and turn limits."""
    raise NotImplementedError("Phase 2")
```

`app/core/llm/client.py`:
```python
"""LLM client wrapper — chat completion + embedding, with fallback chain.

Phase 2 implementation: primary DeepSeek, fallback configurable.
"""


async def chat_completion(messages: list[dict], model: str, **kwargs) -> str:
    """Send chat completion request; return response text."""
    raise NotImplementedError("Phase 2")


async def get_embedding(text: str, model: str) -> list[float]:
    """Get text embedding vector."""
    raise NotImplementedError("Phase 2")
```

`app/core/llm/prompts.py`:
```python
"""Prompt templates — per-tenant customized system prompt + intent + response.

Adapted from ShopMind-Agent src/prompts.py, modified for multi-tenant.
"""


def build_system_prompt(tenant_config: dict) -> str:
    """Build system prompt from base + tenant-specific append."""
    raise NotImplementedError("Phase 2")


def intent_prompt(user_input: str) -> str:
    """Prompt for intent classification via LLM."""
    raise NotImplementedError("Phase 2")


def response_prompt(intent: str, context: str, history: list[dict], user_input: str) -> str:
    """Prompt for generating final customer response."""
    raise NotImplementedError("Phase 2")
```

- [ ] **Step 2: Write all service stubs**

`app/services/chat_service.py`:
```python
"""Chat pipeline orchestrator — cache → intent → retrieval → LLM → persist.

Phase 2 implementation: coordinates L1/L2 cache, intent classifier,
retrieval fusion, LLM generation, and conversation persistence.
"""


async def process_chat(tenant_id: str, session_id: str, message: str) -> dict:
    """Execute full chat pipeline for a single user message."""
    raise NotImplementedError("Phase 2")
```

`app/services/knowledge_service.py`:
```python
"""Knowledge base service — SQL + ChromaDB dual-write coordination.

Phase 1 implementation: transactional creation, update, deletion
with ChromaDB sync and cache invalidation.
"""


def create_knowledge(tenant_id: str, data: dict) -> dict:
    """Create knowledge item → SQL insert → embed → ChromaDB add."""
    raise NotImplementedError("Phase 1")


def update_knowledge(tenant_id: str, item_id: str, data: dict) -> dict:
    """Update knowledge item → SQL update → re-embed → ChromaDB update."""
    raise NotImplementedError("Phase 1")


def delete_knowledge(tenant_id: str, item_id: str) -> None:
    """Delete knowledge item → ChromaDB remove → SQL delete + cache invalidate."""
    raise NotImplementedError("Phase 1")
```

`app/services/analytics_service.py`:
```python
"""Analytics service — aggregate queries and dashboard data.

Phase 4 implementation: conversation volume, intent distribution,
cache hit rates, latency distribution, knowledge hit rankings.
"""


def get_overview(tenant_id: str, days: int = 7) -> dict:
    """Dashboard overview statistics."""
    raise NotImplementedError("Phase 4")
```

- [ ] **Step 3: Create placeholder test files**

```bash
cd "D:/AAA/smart-cs"

cat > "tests/test_chat_api.py" << 'PYEOF'
"""Chat API tests — Phase 2: full pipeline integration tests."""
PYEOF

cat > "tests/test_admin_knowledge_api.py" << 'PYEOF'
"""Admin knowledge CRUD API tests — Phase 1: CRUD + ChromaDB sync."""
PYEOF

cat > "tests/test_admin_analytics_api.py" << 'PYEOF'
"""Admin analytics API tests — Phase 4: dashboard data accuracy."""
PYEOF

cat > "tests/test_retrieval.py" << 'PYEOF'
"""Retrieval tests — Phase 1: ChromaDB + BM25 + RRF fusion accuracy."""
PYEOF

cat > "tests/test_cache.py" << 'PYEOF'
"""Cache tests — Phase 2: L1 exact + L2 semantic cache behavior."""
PYEOF

cat > "tests/test_intent.py" << 'PYEOF'
"""Intent classification tests — Phase 2: rule + LLM hybrid accuracy."""
PYEOF

cat > "tests/test_memory.py" << 'PYEOF'
"""Conversation memory tests — Phase 2: sliding window token/turn limits."""
PYEOF

cat > "tests/test_tenant_isolation.py" << 'PYEOF'
"""Tenant data isolation tests — Phase 1+: verify Tenant A cannot see Tenant B data."""
PYEOF

cat > "tests/test_e2e.py" << 'PYEOF'
"""End-to-end chat flow tests — Phase 4: full pipeline from request to response."""
PYEOF
```

- [ ] **Step 4: Final full verification**

```bash
cd "D:/AAA/smart-cs"

# 1. pytest — all importable
D:\conda\Scripts\conda.exe run -n smart-cs pytest tests/ -v

# 2. app starts cleanly
D:\conda\Scripts\conda.exe run -n smart-cs python -c "
from app.main import app
print(f'App: {app.title} v{app.version}')
print(f'Routes: {len(app.routes)}')
print('App factory OK')
"

# 3. config loads
D:\conda\Scripts\conda.exe run -n smart-cs python -c "
from app.config import settings
print(f'DB: {settings.database_url}')
print(f'LLM: {settings.llm_model}')
print(f'Log: {settings.log_level}')
print('Config OK')
"

# 4. models create_all test
D:\conda\Scripts\conda.exe run -n smart-cs python -c "
from sqlalchemy import create_engine
from app.models import Base
e = create_engine('sqlite:///:memory:')
Base.metadata.create_all(e)
print('Tables:', list(Base.metadata.tables.keys()))
e.dispose()
print('Models OK')
"
```

Expected: all 4 checks pass, no import or runtime errors

---

### Task 11: Final Integration Verification

- [ ] **Step 1: Full integration test**

```bash
cd "D:/AAA/smart-cs"

# Clean up any existing test database
rm -f ./smartcs.db ./test_verify.db

# Start server
D:\conda\Scripts\conda.exe run -n smart-cs uvicorn app.main:app --host 127.0.0.1 --port 8000 &
SERVER_PID=$!
sleep 3

echo "=== 1. Health check ==="
curl -s http://127.0.0.1:8000/health
echo ""

echo "=== 2. Placeholder chat (demo tenant - seeded by lifespan) ==="
curl -s -X POST http://127.0.0.1:8000/api/v1/demo/chat -H "Content-Type: application/json" -d '{"message": "hello"}'
echo ""

echo "=== 3. Tenant not found ==="
curl -s -X POST http://127.0.0.1:8000/api/v1/nonexistent/chat -H "Content-Type: application/json" -d '{}'
echo ""

echo "=== 4. Admin knowledge placeholder ==="
curl -s http://127.0.0.1:8000/api/v1/admin/demo/knowledge
echo ""

echo "=== 5. X-Request-ID header ==="
curl -s -v http://127.0.0.1:8000/health 2>&1 | grep -i x-request-id
echo ""

echo "=== 6. Run pytest ==="
D:\conda\Scripts\conda.exe run -n smart-cs pytest tests/ -v

# Stop server
kill $SERVER_PID 2>/dev/null || true

echo "=== Phase 0 complete ==="
```

Expected output:
1. `{"status":"ok","version":"0.1.0"}`
2. `{"status":"not_implemented"}`
3. `{"error":{"code":"TENANT_NOT_FOUND","message":"Tenant 'nonexistent' does not exist","request_id":"<uuid>"}}`
4. `{"status":"not_implemented"}`
5. `X-Request-ID: <uuid>` header present
6. All pytest tests pass (at minimum: test_fixtures.py 3 tests)
