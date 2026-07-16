"""FastAPI application factory with lifespan management.

Usage:
    uvicorn app.main:app --reload
"""

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.admin.analytics import router as admin_analytics_router
from app.api.admin.auth import router as admin_auth_router
from app.api.admin.document import router as admin_document_router
from app.api.admin.knowledge import router as admin_knowledge_router
from app.api.auth import router as auth_router
from app.api.assistant import router as assistant_router
from app.api.business import router as business_router
from app.api.health import router as health_router
from app.config import settings
from app.middleware.error_handler import register_error_handlers
from app.middleware.logging import LoggingMiddleware, setup_structlog
from app.middleware.ratelimit import RateLimitMiddleware
from app.middleware.tenant import TenantMiddleware

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application lifespan — setup on start, teardown on shutdown."""
    setup_structlog(settings.log_level, settings.log_dir)

    # Import here to avoid circular imports at module level
    from app.db import SessionLocal, engine
    from app.models import Base
    from app.models.tenant import Tenant

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        if db.query(Tenant).count() == 0:
            seed_path = _PROJECT_ROOT / "data" / "seed" / "tenant_sample.json"
            if seed_path.exists():
                with open(seed_path, encoding="utf-8") as f:
                    seed_data = json.load(f)
                db.add(Tenant(**seed_data))
            else:
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

            # Seed FAQ data for demo tenant if knowledge_items is empty
            demo_tenant = db.query(Tenant).filter(Tenant.slug == "demo").first()
            if demo_tenant:
                from app.models.knowledge import KnowledgeItem
                if db.query(KnowledgeItem).filter(KnowledgeItem.tenant_id == demo_tenant.id).count() == 0:
                    faq_path = _PROJECT_ROOT / "data" / "seed" / "enterprise_knowledge.json"
                    if not faq_path.exists():
                        faq_path = _PROJECT_ROOT / "data" / "seed" / "faq_template.json"
                    if faq_path.exists():
                        with open(faq_path, encoding="utf-8") as f:
                            faq_items = json.load(f)
                        for faq in faq_items:
                            db.add(KnowledgeItem(
                                tenant_id=demo_tenant.id,
                                question=faq["question"],
                                answer=faq["answer"],
                                keywords=faq.get("keywords", ""),
                                status="active",
                            ))
                        db.commit()
        demo_tenant = db.query(Tenant).filter(Tenant.slug == "demo").first()
        if demo_tenant:
            from app.services.business_service import seed_demo_crm
            seed_demo_crm(db, demo_tenant.id)
    finally:
        db.close()

    # ---- Initialize retrieval services ----
    from app.core.retrieval_module import (
        set_vector_store,
        set_bm25_manager,
        set_embedding_provider,
        set_l1_cache,
        set_l2_cache,
    )
    from app.core.retrieval.vector_store import VectorStore
    from app.core.retrieval.bm25_index import BM25IndexManager
    from app.core.embedding import get_embedding_provider as get_emb_provider
    from app.core.cache.exact import ExactCache
    from app.core.cache.semantic import SemanticCache
    from app.models.document import Document, DocumentChunk
    from app.models.knowledge import KnowledgeItem

    vector_store = VectorStore(settings.chroma_persist_dir)
    bm25_manager = BM25IndexManager()
    embedding_provider = get_emb_provider(settings)

    set_vector_store(vector_store)
    set_bm25_manager(bm25_manager)
    set_embedding_provider(embedding_provider)

    # ---- Initialize caches ----
    set_l1_cache(ExactCache())
    set_l2_cache(SemanticCache())

    # Build BM25 indices for all existing active tenants
    db = SessionLocal()
    try:
        tenants = db.query(Tenant).filter(Tenant.is_active.is_(True)).all()
        for tenant in tenants:
            knowledge_items = (
                db.query(KnowledgeItem)
                .filter(
                    KnowledgeItem.tenant_id == tenant.id,
                    KnowledgeItem.status == "active",
                )
                .all()
            )
            document_chunks = (
                db.query(DocumentChunk)
                .join(Document, DocumentChunk.document_id == Document.id)
                .filter(
                    Document.tenant_id == tenant.id,
                    Document.status == "ready",
                    DocumentChunk.status == "active",
                )
                .all()
            )
            corpus = [
                (item.embedding_id or str(item.id), f"{item.question} {item.answer}")
                for item in knowledge_items
            ]
            corpus.extend((chunk.embedding_id or str(chunk.id), chunk.content) for chunk in document_chunks)
            if corpus:
                bm25_manager.build(tenant.slug, corpus)
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
    #    Order (request path): Logging -> Tenant -> RateLimit -> route handler.
    #    Tenant must run before RateLimit because the limiter keys on the resolved tenant.
    app.add_middleware(RateLimitMiddleware, rpm=settings.rate_limit_per_minute)
    app.add_middleware(TenantMiddleware)
    app.add_middleware(LoggingMiddleware)    # Added last   -> outermost (wraps everything)

    # 3. Prometheus metrics — auto-instruments HTTP requests
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
    )
    instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    # 4. Include API routers
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(assistant_router)
    app.include_router(business_router)
    app.include_router(admin_auth_router)
    app.include_router(admin_document_router)
    app.include_router(admin_knowledge_router)
    app.include_router(admin_analytics_router)

    # 5. Mount static file directories
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
