"""L2 semantic cache — per-tenant, cosine similarity."""

import math


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


class SemanticCache:
    def __init__(self):
        self._store: dict[str, list[tuple[list[float], str]]] = {}

    def get(self, tenant_id: str, query_emb: list[float], threshold: float = 0.85) -> str | None:
        entries = self._store.get(tenant_id, [])
        best_score, best_answer = 0.0, None
        for emb, answer in entries:
            score = _cosine(query_emb, emb)
            if score > best_score:
                best_score, best_answer = score, answer
        return best_answer if best_score >= threshold else None

    def set(self, tenant_id: str, embedding: list[float], answer: str):
        self._store.setdefault(tenant_id, []).append((embedding, answer))

    def invalidate(self, tenant_id: str):
        self._store.pop(tenant_id, None)
