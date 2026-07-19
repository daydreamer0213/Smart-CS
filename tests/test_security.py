"""Security regression tests for the current public API surface."""

import json

from app.core.auth.security import hash_password
from app.core.auth.token import create_access_token
from app.models.document import Document, DocumentChunk
from app.models.user import User


def _user(db, tenant, email):
    user = User(
        tenant_id=tenant.id,
        email=email,
        password_hash=hash_password("Password123"),
        display_name="Security Test User",
        role="employee",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


async def test_assistant_requires_bearer_token(client, test_tenant):
    response = await client.post(
        f"/api/v1/{test_tenant.slug}/assistant/chat",
        json={"message": "<script>alert(1)</script>"},
    )
    assert response.status_code == 401


async def test_assistant_cross_tenant_access_is_forbidden(client, db, test_tenant):
    from app.models.tenant import Tenant

    user = _user(db, test_tenant, "employee-a@example.com")
    other = Tenant(slug="other-tenant", name="Other", config_json={}, is_active=True)
    db.add(other)
    db.commit()

    response = await client.post(
        f"/api/v1/{other.slug}/assistant/chat",
        headers={"Authorization": f"Bearer {create_access_token(user)}"},
        json={"message": "query knowledge"},
    )
    assert response.status_code == 403


async def test_admin_tenant_slug_injection_is_rejected(client, admin_api_key):
    raw_key, _ = admin_api_key
    response = await client.get(
        "/api/v1/admin/fake-tenant-knowledge/knowledge",
        headers={"X-Admin-Key": raw_key},
    )
    assert response.status_code == 404


async def test_admin_requires_valid_credentials(client, test_tenant):
    response = await client.get(
        f"/api/v1/admin/{test_tenant.slug}/knowledge",
        headers={"Authorization": "Bearer fake-token"},
    )
    assert response.status_code == 401


async def test_search_filters_cross_tenant_document_chunk_ids(db, test_tenant, monkeypatch):
    from app.core.agent.hr_agent import search_hr_knowledge, set_hr_runtime
    from app.models.tenant import Tenant

    try:
        employee = User(
            tenant_id=test_tenant.id,
            email="current-tenant-employee@example.com",
            password_hash=hash_password("Password123"),
            display_name="Security Test User",
            role="employee",
            is_active=True,
        )
        db.add(employee)
        db.flush()
        other_tenant = Tenant(
            slug="other-document-tenant",
            name="Other Document Tenant",
            config_json={},
            is_active=True,
        )
        db.add(other_tenant)
        db.flush()
        current_document = Document(
            tenant_id=test_tenant.id,
            filename="current-tenant-policy.txt",
            file_type="txt",
            file_hash="current-tenant-document-hash",
            status="ready",
        )
        other_document = Document(
            tenant_id=other_tenant.id,
            filename="other-tenant-policy.txt",
            file_type="txt",
            file_hash="other-tenant-document-hash",
            status="ready",
        )
        db.add_all([current_document, other_document])
        db.flush()
        current_content = "Only the current tenant may see this policy."
        other_content = "Only the other tenant may see this policy."
        current_chunk = DocumentChunk(
            document_id=current_document.id,
            chunk_index=0,
            content=current_content,
            status="active",
        )
        other_chunk = DocumentChunk(
            document_id=other_document.id,
            chunk_index=0,
            content=other_content,
            status="active",
        )
        db.add_all([current_chunk, other_chunk])
        db.flush()

        class FakeEmbedding:
            async def embed(self, _texts):
                return [[0.0]]

        class FakeVectorStore:
            def search(self, *_args):
                return [(current_chunk.id, 0.1), (other_chunk.id, 0.2)]

        class FakeBm25:
            def search(self, *_args):
                return [(current_chunk.id, 1.0), (other_chunk.id, 2.0)]

        monkeypatch.setattr("app.core.agent.tools.get_embedding_provider", lambda: FakeEmbedding())
        monkeypatch.setattr("app.core.agent.tools.get_vector_store", lambda: FakeVectorStore())
        monkeypatch.setattr("app.core.agent.tools.get_bm25_manager", lambda: FakeBm25())

        set_hr_runtime(db, test_tenant.id, test_tenant.slug, employee, "What is the leave policy?")
        result = json.loads(await search_hr_knowledge.ainvoke({"query": "leave policy"}))

        sources = result["sources"]
        assert [{key: source[key] for key in ("source_id", "title", "excerpt")} for source in sources] == [
            {
                "source_id": current_chunk.id,
                "title": current_document.filename,
                "excerpt": current_content,
            }
        ]
        assert other_chunk.id not in {source["source_id"] for source in sources}
        assert result["result_count"] == 1
    finally:
        db.rollback()


async def test_search_rejects_high_distance_vector_only_source(db, test_tenant, monkeypatch):
    from app.core.agent.hr_agent import search_hr_knowledge, set_hr_runtime

    employee = _user(db, test_tenant, "distant-vector-employee@example.com")
    document = Document(
        tenant_id=test_tenant.id,
        filename="unrelated-policy.txt",
        file_type="txt",
        file_hash="unrelated-policy-hash",
        status="ready",
    )
    db.add(document)
    db.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        content="This content is unrelated to the query.",
        status="active",
    )
    db.add(chunk)
    db.flush()

    class FakeEmbedding:
        async def embed(self, _texts):
            return [[0.0]]

    class FakeVectorStore:
        def search(self, *_args):
            return [(chunk.id, 0.9)]

    class FakeBm25:
        def search(self, *_args):
            return []

    monkeypatch.setattr("app.core.agent.tools.get_embedding_provider", lambda: FakeEmbedding())
    monkeypatch.setattr("app.core.agent.tools.get_vector_store", lambda: FakeVectorStore())
    monkeypatch.setattr("app.core.agent.tools.get_bm25_manager", lambda: FakeBm25())

    set_hr_runtime(db, test_tenant.id, test_tenant.slug, employee, "leave policy")
    result = json.loads(await search_hr_knowledge.ainvoke({"query": "leave policy"}))

    assert result["status"] == "NO_RESULTS"
    assert result["sources"] == []
    assert result["result_count"] == 0

    class FakeMatchingBm25:
        def search(self, *_args):
            return [(chunk.id, 1.0)]

    monkeypatch.setattr("app.core.agent.tools.get_bm25_manager", lambda: FakeMatchingBm25())
    set_hr_runtime(db, test_tenant.id, test_tenant.slug, employee, "leave policy")
    bm25_result = json.loads(await search_hr_knowledge.ainvoke({"query": "leave policy"}))

    assert bm25_result["status"] == "OK"
    assert [source["source_id"] for source in bm25_result["sources"]] == [chunk.id]


async def test_search_filters_document_chunks_by_audience_role(db, test_tenant, monkeypatch):
    from app.core.agent.hr_agent import search_hr_knowledge, set_hr_runtime

    try:
        employee = User(
            tenant_id=test_tenant.id,
            email="document-role-employee@example.com",
            password_hash=hash_password("Password123"),
            display_name="Document Role Employee",
            role="employee",
            is_active=True,
        )
        admin = User(
            tenant_id=test_tenant.id,
            email="document-role-admin@example.com",
            password_hash=hash_password("Password123"),
            display_name="Document Role Admin",
            role="admin",
            is_active=True,
        )
        restricted_document = Document(
            tenant_id=test_tenant.id,
            filename="admin-policy.txt",
            file_type="txt",
            file_hash="admin-policy-hash",
            status="ready",
            audience_roles=["admin"],
        )
        legacy_document = Document(
            tenant_id=test_tenant.id,
            filename="general-policy.txt",
            file_type="txt",
            file_hash="general-policy-hash",
            status="ready",
            audience_roles=[],
        )
        db.add_all([employee, admin, restricted_document, legacy_document])
        db.flush()
        restricted_chunk = DocumentChunk(
            document_id=restricted_document.id,
            chunk_index=0,
            content="Admin-only policy.",
            status="active",
        )
        legacy_chunk = DocumentChunk(
            document_id=legacy_document.id,
            chunk_index=0,
            content="General policy.",
            status="active",
        )
        db.add_all([restricted_chunk, legacy_chunk])
        db.flush()

        class FakeEmbedding:
            async def embed(self, _texts):
                return [[0.0]]

        class FakeVectorStore:
            def search(self, *_args):
                return [(restricted_chunk.id, 0.2), (legacy_chunk.id, 0.1)]

        class FakeBm25:
            def search(self, *_args):
                return [(restricted_chunk.id, 2.0), (legacy_chunk.id, 1.0)]

        monkeypatch.setattr("app.core.agent.tools.get_embedding_provider", lambda: FakeEmbedding())
        monkeypatch.setattr("app.core.agent.tools.get_vector_store", lambda: FakeVectorStore())
        monkeypatch.setattr("app.core.agent.tools.get_bm25_manager", lambda: FakeBm25())

        set_hr_runtime(db, test_tenant.id, test_tenant.slug, employee, "policy")
        employee_result = json.loads(await search_hr_knowledge.ainvoke({"query": "policy"}))
        employee_sources = {item["source_id"] for item in employee_result["sources"]}
        assert restricted_chunk.id not in employee_sources
        assert legacy_chunk.id in employee_sources

        set_hr_runtime(db, test_tenant.id, test_tenant.slug, admin, "policy")
        admin_result = json.loads(await search_hr_knowledge.ainvoke({"query": "policy"}))
        admin_sources = {item["source_id"] for item in admin_result["sources"]}
        assert restricted_chunk.id in admin_sources
        assert legacy_chunk.id in admin_sources
    finally:
        db.rollback()


async def test_search_provenance_requires_ready_tenant_role_authorized_sql_chunk(
    db, test_tenant, monkeypatch,
):
    from app.core.agent.hr_agent import search_hr_knowledge, set_hr_runtime
    from app.models.tenant import Tenant

    employee = User(
        tenant_id=test_tenant.id,
        email="provenance-security-employee@example.com",
        password_hash=hash_password("Password123"),
        display_name="Provenance Security Employee",
        role="employee",
        is_active=True,
    )
    other_tenant = Tenant(
        slug="provenance-other-tenant",
        name="Provenance Other Tenant",
        config_json={},
        is_active=True,
    )
    db.add_all([employee, other_tenant])
    db.flush()

    documents = [
        Document(tenant_id=test_tenant.id, filename="review.pdf", file_type="pdf", file_hash="review", status="review_required"),
        Document(tenant_id=other_tenant.id, filename="other.pdf", file_type="pdf", file_hash="other", status="ready"),
        Document(tenant_id=test_tenant.id, filename="admin.pdf", file_type="pdf", file_hash="admin", status="ready", audience_roles=["admin"]),
        Document(tenant_id=test_tenant.id, filename="employee.pdf", file_type="pdf", file_hash="employee", status="ready", audience_roles=["employee"]),
    ]
    db.add_all(documents)
    db.flush()
    chunks = [
        DocumentChunk(document_id=document.id, chunk_index=0, content=document.filename, status="active", page_start=index + 1)
        for index, document in enumerate(documents)
    ]
    db.add_all(chunks)
    db.flush()

    class FakeEmbedding:
        async def embed(self, _texts):
            return [[0.0]]

    class FakeVectorStore:
        forged_metadata = {"page_start": 999, "section_path": ["forged"]}

        def search(self, *_args):
            return [(chunk.id, 0.1) for chunk in chunks]

    class FakeBm25:
        def search(self, *_args):
            return [(chunk.id, 1.0) for chunk in chunks]

    monkeypatch.setattr("app.core.agent.tools.get_embedding_provider", lambda: FakeEmbedding())
    monkeypatch.setattr("app.core.agent.tools.get_vector_store", lambda: FakeVectorStore())
    monkeypatch.setattr("app.core.agent.tools.get_bm25_manager", lambda: FakeBm25())

    set_hr_runtime(db, test_tenant.id, test_tenant.slug, employee, "policy")
    payload = json.loads(await search_hr_knowledge.ainvoke({"query": "policy"}))

    assert payload["sources"] == [{
        "source_type": "document",
        "source_id": chunks[3].id,
        "title": "employee.pdf",
        "excerpt": "employee.pdf",
        "score": 0.0312,
        "page_start": 4,
    }]


async def test_search_keeps_authorized_document_after_restricted_candidates(
    db, test_tenant, monkeypatch
):
    from app.core.agent.hr_agent import search_hr_knowledge, set_hr_runtime

    employee = _user(db, test_tenant, "authorized-result-employee@example.com")
    restricted_chunks = []
    for index in range(5):
        document = Document(
            tenant_id=test_tenant.id,
            filename=f"admin-only-{index}.txt",
            file_type="txt",
            file_hash=f"admin-only-candidate-{index}",
            status="ready",
            audience_roles=["admin"],
        )
        db.add(document)
        db.flush()
        chunk = DocumentChunk(
            document_id=document.id,
            chunk_index=0,
            content=f"Admin-only policy {index}.",
            status="active",
        )
        db.add(chunk)
        restricted_chunks.append(chunk)

    visible_document = Document(
        tenant_id=test_tenant.id,
        filename="employee-visible-policy.txt",
        file_type="txt",
        file_hash="employee-visible-candidate",
        status="ready",
        audience_roles=["employee"],
    )
    db.add(visible_document)
    db.flush()
    visible_chunk = DocumentChunk(
        document_id=visible_document.id,
        chunk_index=0,
        content="Employee-visible leave policy.",
        status="active",
    )
    db.add(visible_chunk)
    db.flush()

    ranked_results = [chunk.id for chunk in restricted_chunks] + [visible_chunk.id]

    class FakeEmbedding:
        async def embed(self, _texts):
            return [[0.0]]

    class FakeVectorStore:
        def search(self, _tenant_slug, _query_vec, top_k):
            return [(chunk_id, 0.1) for chunk_id in ranked_results[:top_k]]

    class FakeBm25:
        def search(self, _tenant_slug, _query, top_k):
            return [
                (chunk_id, float(len(ranked_results) - index))
                for index, chunk_id in enumerate(ranked_results[:top_k])
            ]

    monkeypatch.setattr("app.core.agent.tools.get_embedding_provider", lambda: FakeEmbedding())
    monkeypatch.setattr("app.core.agent.tools.get_vector_store", lambda: FakeVectorStore())
    monkeypatch.setattr("app.core.agent.tools.get_bm25_manager", lambda: FakeBm25())

    set_hr_runtime(db, test_tenant.id, test_tenant.slug, employee, "leave policy")
    result = json.loads(await search_hr_knowledge.ainvoke({"query": "leave policy"}))

    assert result["status"] == "OK"
    assert [source["source_id"] for source in result["sources"]] == [visible_chunk.id]
