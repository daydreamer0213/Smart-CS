"""FastAPI application factory with lifespan management.

Usage:
    uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager
from pathlib import Path

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

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application lifespan — setup on start, teardown on shutdown."""
    setup_structlog(settings.log_level)

    # Import here to avoid circular imports at module level
    from app.db import SessionLocal, engine
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
    """Build and return a configured FastAPI application instance."""
    app = FastAPI(
        title="SmartCS",
        version="0.1.0",
        lifespan=lifespan,
    )

    # 1. Register error handlers FIRST (lowest-level, catches everything)
    register_error_handlers(app)

    # 2. Add middlewares.
    #    Starlette applies middlewares in reverse addition order (last added = outermost).
    #    We want: LoggingMiddleware (outermost, wraps everything)
    #             TenantMiddleware (inner, inside logging)
    app.add_middleware(TenantMiddleware)   # Added first  -> inner
    app.add_middleware(LoggingMiddleware)  # Added last   -> outer (wraps everything)

    # 3. Include API routers
    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(admin_knowledge_router)
    app.include_router(admin_analytics_router)

    # 4. Mount static file directories (after routers so routes take priority)
    static_dir = _PROJECT_ROOT / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/static",
        StaticFiles(directory=str(static_dir), html=True),
        name="static",
    )

    admin_static_dir = _PROJECT_ROOT / "admin-static"
    admin_static_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/admin",
        StaticFiles(directory=str(admin_static_dir), html=True),
        name="admin",
    )

    return app


app = create_app()
