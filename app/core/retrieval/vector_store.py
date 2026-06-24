"""ChromaDB vector store management — per-tenant collection isolation.

Phase 1 implementation: CRUD-synchronized, collection naming {tenant_slug}_knowledge.
"""


def get_collection(tenant_slug: str):
    """Get or create the ChromaDB collection for a tenant."""
    raise NotImplementedError("Phase 1")
