"""Pytest fixtures for SmartCS tests.

Provides in-memory SQLite database patching, tenant seeding, and
async HTTP client for end-to-end API testing without a real database.
"""

import hashlib
import uuid
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import create_app
from app.models import Base
from app.models.tenant import AdminApiKey, Tenant


@pytest.fixture(scope="session")
def engine():
    """In-memory SQLite engine — fresh database per test session.

    Patches ``app.db.engine``, ``app.db.SessionLocal`` **and** all
    module-level ``SessionLocal`` references in modules imported at
    startup (``app.api.deps``, ``app.middleware.tenant``,
    ``app.api.admin.auth``) so that middleware, route deps, and verify_admin
    all hit the shared in-memory database.
    """
    from app import db as app_db

    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)

    # ---- patch module-level singletons ----
    app_db.engine = eng
    app_db.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=eng)

    # Modules that were imported at conftest load time already captured
    # ``from app.db import SessionLocal`` as a local reference.  Patch
    # those references so that TenantMiddleware, get_db, and verify_admin
    # all use the in-memory engine.
    import app.api.admin.auth
    import app.api.deps
    import app.middleware.tenant

    new_sm = app_db.SessionLocal
    app.api.deps.SessionLocal = new_sm
    app.middleware.tenant.SessionLocal = new_sm
    app.api.admin.auth.SessionLocal = new_sm

    return eng


@pytest.fixture
def db(engine) -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session with automatic rollback on teardown.

    Data committed through this session is visible to the running application
    (middleware, API dependencies, etc.) because ``app.db.SessionLocal`` has
    been patched to point at the same in-memory engine.

    After the test the session is rolled back and closed.  Note that a
    ``commit()`` performed *inside* the test is a real commit to the shared
    in-memory database and therefore survives the per-test rollback.
    Upcoming tests that rely on ``test_tenant`` should use the fixture's
    built-in cleanup (see ``test_tenant``) for isolation.
    """
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def test_tenant(db: Session) -> Generator[Tenant, None, None]:
    """Seed and yield a demo tenant, then clean it up after the test.

    The tenant is committed to the shared in-memory database so it is
    discoverable by ``TenantMiddleware`` during the test.  After the test
    fixture teardown deletes the row so that subsequent tests receive a
    clean slate.
    """
    slug = f"test-tenant-{uuid.uuid4().hex[:8]}"
    tenant = Tenant(
        id=str(uuid.uuid4()),
        slug=slug,
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

    yield tenant

    # ---- cleanup ----
    db.delete(tenant)
    db.commit()


@pytest.fixture
def app(engine) -> Generator:
    """Build a fresh FastAPI application via the factory.

    Dependency overrides are cleared so the app uses ``app.db.SessionLocal``
    (already patched by ``engine`` fixture) for all database access.
    """
    test_app = create_app()
    test_app.dependency_overrides = {}
    yield test_app


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client using ASGITransport — no server process needed."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def admin_api_key(db: Session, test_tenant: Tenant) -> tuple[str, AdminApiKey]:
    """Create and yield an admin API key for the test tenant.  The raw key
    is randomized per test so that each invocation gets a unique key hash
    and never collides with earlier fixture commits that survive into the
    shared in-memory database.
    """
    raw_key = f"test-admin-key-{uuid.uuid4().hex[:8]}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = AdminApiKey(tenant_id=test_tenant.id, key_hash=key_hash, label="test-key")
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    return raw_key, api_key


@pytest_asyncio.fixture
async def admin_client(app, engine, db, admin_api_key):
    """Async HTTP client pre-configured with ``X-Admin-Key`` header."""
    raw_key, _ = admin_api_key
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"X-Admin-Key": raw_key}
    ) as ac:
        yield ac
