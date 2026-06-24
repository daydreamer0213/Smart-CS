"""Knowledge base service — SQL + ChromaDB dual-write coordination.

Phase 1 implementation: transactional creation, update, deletion
with ChromaDB sync and cache invalidation.
"""


def create_knowledge(tenant_id: str, data: dict) -> dict:
    """Create knowledge item -> SQL insert -> embed -> ChromaDB add."""
    raise NotImplementedError("Phase 1")


def update_knowledge(tenant_id: str, item_id: str, data: dict) -> dict:
    """Update knowledge item -> SQL update -> re-embed -> ChromaDB update."""
    raise NotImplementedError("Phase 1")


def delete_knowledge(tenant_id: str, item_id: str) -> None:
    """Delete knowledge item -> ChromaDB remove -> SQL delete + cache invalidate."""
    raise NotImplementedError("Phase 1")
