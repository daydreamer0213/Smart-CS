"""BM25 keyword index with per-tenant in-memory instances."""

import jieba
import threading
from rank_bm25 import BM25Okapi


def _tokenize(text: str) -> list[str]:
    tokens = [t.strip().lower() for t in jieba.lcut(text) if t.strip()]
    return [t for t in tokens if len(t) > 1 or t.isalnum()]


class BM25IndexManager:
    def __init__(self):
        self._indexes: dict[str, BM25Okapi] = {}
        self._doc_ids: dict[str, list[str]] = {}
        self._corpora: dict[str, dict[str, str]] = {}
        self._lock = threading.RLock()

    def _rebuild(self, tenant_slug: str, corpus: list[tuple[str, str]]) -> None:
        if not corpus:
            self._indexes.pop(tenant_slug, None)
            self._doc_ids.pop(tenant_slug, None)
            self._corpora.pop(tenant_slug, None)
            return
        current = dict(corpus)
        self._corpora[tenant_slug] = current
        self._doc_ids[tenant_slug] = list(current)
        tokenized = [_tokenize(text) for text in current.values()]
        self._indexes[tenant_slug] = BM25Okapi(tokenized)

    def build(self, tenant_slug: str, corpus: list[tuple[str, str]]) -> None:
        with self._lock:
            self._rebuild(tenant_slug, corpus)

    def has_index(self, tenant_slug: str) -> bool:
        with self._lock:
            return tenant_slug in self._indexes

    def search(
        self, tenant_slug: str, query: str, top_k: int = 5
    ) -> list[tuple[str, float]]:
        with self._lock:
            if tenant_slug not in self._indexes:
                return []
            query_tokens = _tokenize(query)
            if not query_tokens:
                return []
            scores = self._indexes[tenant_slug].get_scores(query_tokens)
            doc_ids = self._doc_ids[tenant_slug]
            ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
            return [
                (doc_ids[idx], score) for idx, score in ranked[:top_k] if score > 0
            ]

    def add(self, tenant_slug: str, doc_id: str, text: str) -> None:
        with self._lock:
            current = dict(self._corpora.get(tenant_slug, {}))
            current[doc_id] = text
            self._rebuild(tenant_slug, list(current.items()))

    def remove(self, tenant_slug: str, doc_id: str) -> None:
        with self._lock:
            current = dict(self._corpora.get(tenant_slug, {}))
            if doc_id not in current:
                return
            current.pop(doc_id)
            self._rebuild(tenant_slug, list(current.items()))

    def remove_tenant(self, tenant_slug: str) -> None:
        """Drop a tenant's BM25 index entirely to reclaim memory."""
        with self._lock:
            self._indexes.pop(tenant_slug, None)
            self._doc_ids.pop(tenant_slug, None)
            self._corpora.pop(tenant_slug, None)
