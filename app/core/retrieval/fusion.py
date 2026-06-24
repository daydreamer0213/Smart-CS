"""RRF (Reciprocal Rank Fusion) — merges vector and BM25 results.

Phase 1 implementation: k=60 constant, top_k configurable.
"""


def rrf_fusion(
    vector_results: list[tuple[str, float]],
    bm25_results: list[tuple[int, float]],
    k: int = 60,
    top_k: int = 5,
) -> list[dict]:
    """Fuse ChromaDB and BM25 results using RRF, returning top_k documents."""
    raise NotImplementedError("Phase 1")
