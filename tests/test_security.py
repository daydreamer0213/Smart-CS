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

    other_tenant = Tenant(
        slug="other-document-tenant",
        name="Other Document Tenant",
        config_json={},
        is_active=True,
    )
    db.add(other_tenant)
    db.flush()
    employee = _user(db, test_tenant, "current-tenant-employee@example.com")
    document = Document(
        tenant_id=other_tenant.id,
        filename="other-tenant-policy.txt",
        file_type="txt",
        file_hash="other-tenant-document-hash",
        status="ready",
    )
    db.add(document)
    db.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        content="Only the other tenant may see this policy.",
        status="active",
    )
    db.add(chunk)
    db.commit()

    class FakeEmbedding:
        async def embed(self, _texts):
            return [[0.0]]

    class FakeVectorStore:
        def search(self, *_args):
            return [(chunk.id, 0.1)]

    class FakeBm25:
        def search(self, *_args):
            return [(chunk.id, 1.0)]

    monkeypatch.setattr("app.core.agent.tools.get_embedding_provider", lambda: FakeEmbedding())
    monkeypatch.setattr("app.core.agent.tools.get_vector_store", lambda: FakeVectorStore())
    monkeypatch.setattr("app.core.agent.tools.get_bm25_manager", lambda: FakeBm25())

    set_hr_runtime(db, test_tenant.id, test_tenant.slug, employee, "What is the leave policy?")
    result = json.loads(await search_hr_knowledge.ainvoke({"query": "leave policy"}))

    assert result["sources"] == []
    assert result["result_count"] == 0
