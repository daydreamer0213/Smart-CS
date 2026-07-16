"""Retrieval pipeline tests: ChromaDB + BM25 + RRF fusion."""


def test_bm25_build_and_search():
    from app.core.retrieval.bm25_index import BM25IndexManager

    bm = BM25IndexManager()
    corpus = [
        ("1", "退货政策 七天无理由退货"),
        ("2", "物流查询 快递单号追踪"),
        ("3", "尺码表 测量方法说明"),
    ]
    bm.build("test", corpus)
    results = bm.search("test", "如何退货", top_k=2)
    assert len(results) > 0
    assert results[0][0] == "1"


def test_bm25_incremental_add_keeps_existing_documents():
    from app.core.retrieval.bm25_index import BM25IndexManager

    bm = BM25IndexManager()
    bm.add("test", "travel", "travel expense reimbursement policy")
    bm.add("test", "contract", "supplier contract approval process")
    bm.add("test", "access", "system access request process")

    results = bm.search("test", "travel reimbursement")
    assert results[0][0] == "travel"


def test_rrf_fusion():
    from app.core.retrieval.fusion import rrf_fusion

    vector = [("a", 0.9), ("b", 0.8), ("c", 0.3)]
    bm25 = [("a", 10.0), ("c", 8.0), ("d", 5.0)]
    fused = rrf_fusion(vector, bm25, top_k=3)
    assert len(fused) == 3
    assert fused[0]["doc_id"] == "a"
    assert "vector" in fused[0]["sources"]


async def test_vector_store_crud():
    import shutil
    import tempfile

    tmp = tempfile.mkdtemp()
    try:
        from app.core.retrieval.vector_store import VectorStore

        vs = VectorStore(tmp)
        vs.add("test", "doc1", [0.1, 0.2, 0.3], {"title": "FAQ1"})
        results = vs.search("test", [0.1, 0.2, 0.3], top_k=1)
        assert len(results) == 1
        assert results[0][0] == "doc1"
        vs.delete("test", "doc1")
        results2 = vs.search("test", [0.1, 0.2, 0.3])
        assert len(results2) == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_tenant_isolation_vector_store():
    import shutil
    import tempfile

    tmp = tempfile.mkdtemp()
    try:
        from app.core.retrieval.vector_store import VectorStore

        vs = VectorStore(tmp)
        vs.add("tenant_a", "a1", [1.0, 0.0], {"_dummy": "a"})
        vs.add("tenant_b", "b1", [0.0, 1.0], {"_dummy": "b"})
        results_a = vs.search("tenant_a", [1.0, 0.0], top_k=5)
        results_b = vs.search("tenant_b", [1.0, 0.0], top_k=5)
        assert results_a[0][0] == "a1"
        assert results_b[0][0] == "b1"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
