"""Knowledge base service — SQL CRUD with optional ChromaDB + BM25 sync.

When *tenant_slug* is provided to ``create_knowledge``, ``update_knowledge``,
or ``delete_knowledge``, the service performs a dual-write: the SQL
transaction is committed only after the corresponding vector-store / BM25
operation succeeds.  If the sync fails the SQL transaction is rolled back,
ensuring the two stores stay consistent.
"""

import asyncio
import concurrent.futures

import structlog
from sqlalchemy.orm import Session

logger = structlog.get_logger()

from app.models.knowledge import Category, KnowledgeItem
from app.schemas.knowledge import (
    CategoryCreate,
    KnowledgeCreate,
    KnowledgeListParams,
    KnowledgeUpdate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_stores():
    """Lazy-import and return the three retrieval singletons.

    Returns ``(None, None, None)`` when the retrieval module has not been
    initialised (e.g. during testing or before the app lifespan has run).
    Callers check for ``None`` and skip the sync in that case.
    """
    from app.core.retrieval_module import (
        get_bm25_manager,
        get_embedding_provider,
        get_vector_store,
    )
    try:
        vs = get_vector_store()
        bm25 = get_bm25_manager()
        emb = get_embedding_provider()
    except (AssertionError, RuntimeError):
        return None, None, None
    return vs, bm25, emb


def _run_async(coro):
    """Run an async coroutine synchronously.

    Handles the common case where this function is called from an already-
    running event loop (e.g. inside an async FastAPI route handler) by
    spinning up a temporary thread with its own event loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — safe to use asyncio.run() directly
        return asyncio.run(coro)

    # Running in an async context — submit to a fresh thread
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result()


def _sync_add(item: KnowledgeItem, tenant_slug: str) -> None:
    """Sync a newly created item to vector store and BM25 index.

    No-op when the retrieval stores have not been initialised
    (e.g. in unit tests without a lifespan).
    """
    vs, bm25, emb = _get_stores()
    if vs is None:
        return
    text = f"{item.question}\n{item.answer}"
    embedding = _run_async(emb.embed([text]))[0]
    doc_id = str(item.id)
    vs.add(
        tenant_slug,
        doc_id,
        embedding,
        {
            "question": item.question,
            "answer": item.answer,
            "keywords": item.keywords or "",
        },
    )
    bm25.add(tenant_slug, doc_id, text)
    item.embedding_id = doc_id


def _sync_update(item: KnowledgeItem, update_data: dict, tenant_slug: str) -> None:
    """Re-sync a knowledge item if question or answer changed.

    When only metadata (e.g. status, category_id) has changed the call is
    a no-op — BM25 / vector-store content is not touched.
    No-op when the retrieval stores have not been initialised.
    """
    content_changed = "question" in update_data or "answer" in update_data
    if not content_changed:
        return

    vs, bm25, emb = _get_stores()
    if vs is None:
        return
    text = f"{item.question}\n{item.answer}"
    embedding = _run_async(emb.embed([text]))[0]
    doc_id = str(item.id)
    vs.update(
        tenant_slug,
        doc_id,
        embedding,
        {
            "question": item.question,
            "answer": item.answer,
            "keywords": item.keywords or "",
        },
    )
    # BM25IndexManager.add rebuilds the whole index so the sequence
    # remove → add effectively performs an update.
    bm25.remove(tenant_slug, doc_id)
    bm25.add(tenant_slug, doc_id, text)


def _sync_remove(item: KnowledgeItem, tenant_slug: str) -> None:
    """Remove a knowledge item from vector store and BM25 index.

    No-op when the retrieval stores have not been initialised.
    """
    vs, bm25, _ = _get_stores()
    if vs is None:
        return
    doc_id = str(item.id)
    vs.delete(tenant_slug, doc_id)
    bm25.remove(tenant_slug, doc_id)
    item.embedding_id = None


# ---------------------------------------------------------------------------
# Public CRUD
# ---------------------------------------------------------------------------

def create_knowledge(
    db: Session,
    tenant_id: str,
    data: KnowledgeCreate,
    tenant_slug: str = "",
) -> KnowledgeItem:
    """Create a knowledge item and optionally sync to retrieval stores.

    When *tenant_slug* is non-empty the vector-store / BM25 sync is
    performed *before* the SQL commit.  If either sync fails the SQL
    transaction is rolled back.
    """
    item = KnowledgeItem(
        tenant_id=tenant_id,
        category_id=data.category_id,
        question=data.question,
        answer=data.answer,
        keywords=data.keywords or "",
        status="active",
    )
    db.add(item)

    if tenant_slug:
        db.flush()  # materialise the PK so we can pass it to ChromaDB
        try:
            _sync_add(item, tenant_slug)
        except Exception:
            db.rollback()
            raise

    db.commit()
    db.refresh(item)
    logger.info("knowledge_created", item_id=item.id, tenant_slug=tenant_slug or "none")
    return item


def update_knowledge(
    db: Session,
    item_id: str,
    data: KnowledgeUpdate,
    tenant_slug: str = "",
) -> KnowledgeItem | None:
    """Update a knowledge item and optionally re-sync retrieval stores.

    Only re-embeds and re-syncs when question or answer has changed.
    Metadata-only updates (status, category_id) skip the retrieval sync.
    """
    item = db.query(KnowledgeItem).filter(KnowledgeItem.id == item_id).first()
    if item is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(item, key, value)

    if tenant_slug:
        db.flush()
        try:
            _sync_update(item, update_data, tenant_slug)
        except Exception:
            db.rollback()
            raise

    db.commit()
    db.refresh(item)
    logger.info("knowledge_updated", item_id=item.id, fields=list(update_data.keys()))
    return item


def delete_knowledge(
    db: Session,
    item_id: str,
    tenant_slug: str = "",
) -> KnowledgeItem | None:
    """Soft-delete a knowledge item and optionally remove from retrieval stores."""
    item = db.query(KnowledgeItem).filter(KnowledgeItem.id == item_id).first()
    if item is None:
        return None
    item.status = "archived"

    if tenant_slug:
        db.flush()
        try:
            _sync_remove(item, tenant_slug)
        except Exception:
            db.rollback()
            raise

    db.commit()
    db.refresh(item)
    logger.info("knowledge_deleted", item_id=item.id, tenant_slug=tenant_slug or "none")
    return item


def get_knowledge(db: Session, item_id: str) -> KnowledgeItem | None:
    """Fetch a single knowledge item by ID."""
    return db.query(KnowledgeItem).filter(KnowledgeItem.id == item_id).first()


def list_knowledge(
    db: Session, tenant_id: str, params: KnowledgeListParams
) -> tuple[list[KnowledgeItem], int]:
    """Paginated search + filter over knowledge items (read-only, no sync)."""
    query = db.query(KnowledgeItem).filter(
        KnowledgeItem.tenant_id == tenant_id,
        KnowledgeItem.status != "archived",
    )
    if params.q:
        like = f"%{params.q}%"
        query = query.filter(
            KnowledgeItem.question.ilike(like) | KnowledgeItem.keywords.ilike(like)
        )
    if params.category_id:
        query = query.filter(KnowledgeItem.category_id == params.category_id)
    if params.status:
        query = query.filter(KnowledgeItem.status == params.status)

    total = query.count()
    items = (
        query.order_by(KnowledgeItem.updated_at.desc())
        .offset((params.page - 1) * params.page_size)
        .limit(params.page_size)
        .all()
    )
    return items, total


def create_category(db: Session, tenant_id: str, data: CategoryCreate) -> Category:
    """Create a knowledge category."""
    cat = Category(
        tenant_id=tenant_id,
        name=data.name,
        description=data.description or "",
        sort_order=data.sort_order or 0,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def list_categories(db: Session, tenant_id: str) -> list[Category]:
    """List all categories for a tenant, ordered by sort_order."""
    return (
        db.query(Category)
        .filter(Category.tenant_id == tenant_id)
        .order_by(Category.sort_order.asc())
        .all()
    )
