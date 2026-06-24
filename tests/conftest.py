"""Pytest fixtures for SmartCS tests.

Provides in-memory SQLite database patching, tenant seeding, and
async HTTP client for end-to-end API testing without a real database.
"""

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
from app.models.tenant import Tenant


@pytest.fixture(scope="session")
def engine():
    """In-memory SQLite engine — fresh database per test session.

    Patches ``app.db.engine`` and ``app.db.SessionLocal`` at module level so
    that **all** code paths (``TenantMiddleware``, ``get_db`` dependency,
    lifespan hooks) share the same in-memory database during tests.
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
