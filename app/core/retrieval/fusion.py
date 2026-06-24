"""RRF (Reciprocal Rank Fusion) merges vector and BM25 results."""


def rrf_fusion(
    vector_results: list[tuple[str, float]],
    bm25_results: list[tuple[str, float]],
    k: int = 60,
    top_k: int = 5,
) -> list[dict]:
    scores: dict[str, tuple[float, set[str]]] = {}

    for rank, (doc_id, _) in enumerate(vector_results, start=1):
        entry = scores.setdefault(doc_id, (0.0, set()))
        scores[doc_id] = (entry[0] + 1.0 / (k + rank), entry[1] | {"vector"})

    for rank, (doc_id, _) in enumerate(bm25_results, start=1):
        entry = scores.setdefault(doc_id, (0.0, set()))
        scores[doc_id] = (entry[0] + 1.0 / (k + rank), entry[1] | {"bm25"})

    ranked = sorted(scores.items(), key=lambda x: x[1][0], reverse=True)
    return [
        {"doc_id": doc_id, "score": round(score, 4), "sources": sorted(sources)}
        for doc_id, (score, sources) in ranked[:top_k]
    ]
