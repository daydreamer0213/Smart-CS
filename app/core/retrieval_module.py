"""Singleton accessors for retrieval services, set during lifespan.

Usage:
    from app.core.retrieval_module import (
        set_vector_store, get_vector_store,
        set_bm25_manager, get_bm25_manager,
        set_embedding_provider, get_embedding_provider,
    )

    # Called once during application startup (in lifespan):
    set_vector_store(VectorStore(...))
    set_bm25_manager(BM25IndexManager())
    set_embedding_provider(get_embedding_provider(settings))

    # Called from anywhere after lifespan init:
    vs = get_vector_store()
    bm25 = get_bm25_manager()
    emb = get_embedding_provider()
"""

from app.core.cache.exact import ExactCache
from app.core.cache.semantic import SemanticCache
from app.core.retrieval.vector_store import VectorStore
from app.core.retrieval.bm25_index import BM25IndexManager
from app.core.embedding.base import BaseEmbeddingProvider

_vector_store: VectorStore | None = None
_bm25_manager: BM25IndexManager | None = None
_embedding_provider: BaseEmbeddingProvider | None = None
_l1_cache: ExactCache | None = None
_l2_cache: SemanticCache | None = None


def set_vector_store(store: VectorStore) -> None:
    global _vector_store
    _vector_store = store


def get_vector_store() -> VectorStore:
    assert _vector_store is not None, "VectorStore not initialized"
    return _vector_store


def set_bm25_manager(manager: BM25IndexManager) -> None:
    global _bm25_manager
    _bm25_manager = manager


def get_bm25_manager() -> BM25IndexManager:
    assert _bm25_manager is not None, "BM25IndexManager not initialized"
    return _bm25_manager


def set_embedding_provider(provider: BaseEmbeddingProvider) -> None:
    global _embedding_provider
    _embedding_provider = provider


def get_embedding_provider() -> BaseEmbeddingProvider:
    assert _embedding_provider is not None, "EmbeddingProvider not initialized"
    return _embedding_provider


def set_l1_cache(cache: ExactCache) -> None:
    global _l1_cache
    _l1_cache = cache


def get_l1_cache() -> ExactCache | None:
    return _l1_cache


def set_l2_cache(cache: SemanticCache) -> None:
    global _l2_cache
    _l2_cache = cache


def get_l2_cache() -> SemanticCache | None:
    return _l2_cache
