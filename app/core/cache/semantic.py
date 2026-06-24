"""L2 semantic cache — per-tenant, cosine-similarity threshold.

Phase 2 implementation: embedding -> cosine_similarity(question, cached_embeddings).
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
