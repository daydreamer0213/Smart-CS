"""L1 exact-match cache — per-tenant, TTL-based expiration.

Phase 2 implementation: key = (tenant_id, normalized_question).
Invalidated on knowledge update for that tenant.
"""


def get(tenant_id: str, question: str):
    """Look up exact cache. Returns cached answer or None."""
    raise NotImplementedError("Phase 2")


def set(tenant_id: str, question: str, answer: str, ttl: int = 300) -> None:
    """Store exact cache entry with TTL."""
    raise NotImplementedError("Phase 2")


def invalidate(tenant_id: str) -> None:
    """Clear all cache entries for a tenant (called on knowledge change)."""
    raise NotImplementedError("Phase 2")
