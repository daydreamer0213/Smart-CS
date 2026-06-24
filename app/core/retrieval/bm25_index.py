"""BM25 keyword index with per-tenant in-memory instances."""

import jieba
from rank_bm25 import BM25Okapi


def _tokenize(text: str) -> list[str]:
    tokens = [t.strip().lower() for t in jieba.lcut(text) if t.strip()]
    return [t for t in tokens if len(t) > 1 or t.isalnum()]


class BM25IndexManager:
    def __init__(self):
        self._indexes: dict[str, BM25Okapi] = {}
        self._doc_ids: dict[str, list[str]] = {}

    def _rebuild(self, tenant_slug: str, corpus: list[tuple[str, str]]) -> None:
        if not corpus:
            self._indexes.pop(tenant_slug, None)
            self._doc_ids.pop(tenant_slug, None)
            return
        self._doc_ids[tenant_slug] = [doc_id for doc_id, _ in corpus]
        tokenized = [_tokenize(text) for _, text in corpus]
        self._indexes[tenant_slug] = BM25Okapi(tokenized)

    def build(self, tenant_slug: str, corpus: list[tuple[str, str]]) -> None:
        self._rebuild(tenant_slug, corpus)

    def has_index(self, tenant_slug: str) -> bool:
        return tenant_slug in self._indexes

    def search(
        self, tenant_slug: str, query: str, top_k: int = 5
    ) -> list[tuple[str, float]]:
        if not self.has_index(tenant_slug):
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
        if self.has_index(tenant_slug):
            current = [(did, "") for did in self._doc_ids.get(tenant_slug, [])]
            current.append((doc_id, text))
            self._rebuild(tenant_slug, current)
        else:
            self._rebuild(tenant_slug, [(doc_id, text)])

    def remove(self, tenant_slug: str, doc_id: str) -> None:
        if not self.has_index(tenant_slug):
            return
        current = [
            (did, "") for did in self._doc_ids.get(tenant_slug, []) if did != doc_id
        ]
        self._rebuild(tenant_slug, current)

    def remove_tenant(self, tenant_slug: str) -> None:
        """Drop a tenant's BM25 index entirely to reclaim memory."""
        self._indexes.pop(tenant_slug, None)
        self._doc_ids.pop(tenant_slug, None)
