"""Provenance tests for the SQL-authorized agent retrieval tool."""

import json

from app.core.auth.security import hash_password
from app.models.document import Document, DocumentChunk
from app.models.user import User


def _employee(db, tenant):
    user = User(
        tenant_id=tenant.id,
        email=f"agent-tools-{tenant.id[:8]}@example.com",
        password_hash=hash_password("Password123"),
        display_name="Agent Tools Employee",
        role="employee",
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _stub_retrievers(monkeypatch, chunk_ids):
    class FakeEmbedding:
        async def embed(self, _texts):
            return [[0.0]]

    class FakeVectorStore:
        def search(self, *_args):
            return [(chunk_id, 0.1) for chunk_id in chunk_ids]

    class FakeBm25:
        def search(self, *_args):
            return [(chunk_id, 1.0) for chunk_id in chunk_ids]

    monkeypatch.setattr("app.core.agent.tools.get_embedding_provider", lambda: FakeEmbedding())
    monkeypatch.setattr("app.core.agent.tools.get_vector_store", lambda: FakeVectorStore())
    monkeypatch.setattr("app.core.agent.tools.get_bm25_manager", lambda: FakeBm25())


async def test_search_returns_sql_provenance_not_forged_fused_candidate_provenance(
    db, test_tenant, monkeypatch,
):
    from app.core.agent.tools import search_knowledge, set_runtime

    user = _employee(db, test_tenant)
    document = Document(
        tenant_id=test_tenant.id,
        filename="leave-policy.pdf",
        file_type="pdf",
        file_hash="agent-tools-provenance",
        status="ready",
    )
    db.add(document)
    db.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        content="Annual leave policy.",
        status="active",
        page_start=4,
        page_end=5,
        section_path=["HR", "Leave"],
        element_types=["paragraph", "table"],
    )
    db.add(chunk)
    db.flush()
    _stub_retrievers(monkeypatch, [chunk.id])
    monkeypatch.setattr(
        "app.core.agent.tools.rrf_fusion",
        lambda *_args, **_kwargs: [{
            "doc_id": chunk.id,
            "score": 0.0328,
            "sources": ["bm25", "vector"],
            "page_start": 99,
            "page_end": 100,
            "section_path": ["forged"],
            "element_types": ["forged"],
        }],
    )

    set_runtime(test_tenant.slug, db, user.role, test_tenant.id)
    payload = json.loads(await search_knowledge.ainvoke({"query": "annual leave"}))

    assert payload["results"] == [{
        "id": chunk.id,
        "source_type": "document",
        "document_id": document.id,
        "title": document.filename,
        "chunk_index": 0,
        "content": "Annual leave policy.",
        "page_start": 4,
        "page_end": 5,
        "section_path": ["HR", "Leave"],
        "element_types": ["paragraph", "table"],
        "score": 0.0328,
        "retrievers": ["bm25", "vector"],
    }]


async def test_search_omits_provenance_for_legacy_document_chunk(db, test_tenant, monkeypatch):
    from app.core.agent.tools import search_knowledge, set_runtime

    user = _employee(db, test_tenant)
    document = Document(
        tenant_id=test_tenant.id,
        filename="legacy-policy.txt",
        file_type="txt",
        file_hash="agent-tools-legacy",
        status="ready",
    )
    db.add(document)
    db.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        content="Legacy policy.",
        status="active",
    )
    db.add(chunk)
    db.flush()
    _stub_retrievers(monkeypatch, [chunk.id])

    set_runtime(test_tenant.slug, db, user.role, test_tenant.id)
    result = json.loads(await search_knowledge.ainvoke({"query": "legacy policy"}))["results"][0]

    assert all(field not in result for field in (
        "page_start", "page_end", "section_path", "element_types",
    ))
