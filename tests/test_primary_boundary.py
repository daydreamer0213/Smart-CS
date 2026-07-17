"""Regression tests for the single authenticated Assistant surface."""

import json

from app.config import settings
from app.core.auth.security import hash_password
from app.core.auth.token import create_access_token
from app.models.document import Document, DocumentChunk
from app.models.user import User


def _employee(db, tenant):
    user = User(
        tenant_id=tenant.id,
        email=f"employee-{tenant.id[:8]}@example.com",
        password_hash=hash_password("Password123"),
        display_name="Employee",
        role="employee",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


async def test_assistant_route_is_rate_limited(engine, db, test_tenant, monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    user = _employee(db, test_tenant)

    async def fake_hr_agent(*_args, **_kwargs):
        return "ok", None, []

    old_limit = settings.rate_limit_per_minute
    settings.rate_limit_per_minute = 1
    monkeypatch.setattr("app.api.assistant.run_hr_agent", fake_hr_agent)
    try:
        app = create_app()
        headers = {"Authorization": f"Bearer {create_access_token(user)}"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.post(
                f"/api/v1/{test_tenant.slug}/assistant/chat",
                headers=headers,
                json={"message": "first"},
            )
            business = await client.post(
                f"/api/v1/{test_tenant.slug}/business/chat",
                headers=headers,
                json={"message": "second"},
            )
    finally:
        settings.rate_limit_per_minute = old_limit

    assert first.status_code == 200
    assert business.status_code == 429


async def test_primary_assistant_does_not_expose_crm_confirmation(client, db, test_tenant):
    user = _employee(db, test_tenant)
    response = await client.post(
        f"/api/v1/{test_tenant.slug}/assistant/action-drafts/not-an-hr-draft/confirm",
        headers={
            "Authorization": f"Bearer {create_access_token(user)}",
            "Idempotency-Key": "legacy-crm-0001",
        },
    )

    assert response.status_code == 404


async def test_search_knowledge_returns_document_chunk(db, test_tenant, monkeypatch):
    import app.core.agent.tools as tools

    document = Document(
        tenant_id=test_tenant.id,
        filename="travel-policy.txt",
        file_type="txt",
        file_hash="document-search-hash",
        status="ready",
    )
    db.add(document)
    db.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=1,
        content="Travel expenses must be submitted within seven days.",
        status="active",
    )
    db.add(chunk)
    db.commit()

    class FakeEmbedding:
        async def embed(self, _texts):
            return [[0.0]]

    class FakeStore:
        def search(self, *_args):
            return [(chunk.id, 0.1)]

    class FakeBm25:
        def search(self, *_args):
            return []

    monkeypatch.setattr("app.core.agent.tools.get_embedding_provider", lambda: FakeEmbedding())
    monkeypatch.setattr("app.core.agent.tools.get_vector_store", lambda: FakeStore())
    monkeypatch.setattr("app.core.agent.tools.get_bm25_manager", lambda: FakeBm25())

    tools.set_runtime(test_tenant.slug, db, role="employee", tenant_id=test_tenant.id)
    result = json.loads(await tools.search_knowledge.ainvoke({"query": "travel expenses"}))

    assert result["results"] == [{
        "id": chunk.id,
        "source_type": "document",
        "document_id": document.id,
        "title": document.filename,
        "chunk_index": 1,
        "content": chunk.content,
        "score": 0.0164,
        "retrievers": ["vector"],
    }]
