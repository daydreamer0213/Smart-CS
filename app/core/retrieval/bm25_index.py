"""BM25 keyword index — per-tenant in-memory instances.

Phase 1 implementation: builds on startup from active knowledge items,
rebuilds on knowledge change.
"""


def build_index(tenant_id: str, documents: list[str]):
    """Build BM25 index from tokenized documents for a tenant."""
    raise NotImplementedError("Phase 1")


def search(query: str, tenant_id: str, top_k: int = 5):
    """Search BM25 index for a tenant, return top_k (idx, score) pairs."""
    raise NotImplementedError("Phase 1")
