"""Admin knowledge CRUD API tests."""


async def test_create_knowledge(admin_client, test_tenant):
    response = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/knowledge",
        json={"question": "How to return?", "answer": "Return within 7 days"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["question"] == "How to return?"
    assert data["status"] == "active"
    assert "id" in data


async def test_list_knowledge_empty(admin_client, test_tenant):
    response = await admin_client.get(f"/api/v1/admin/{test_tenant.slug}/knowledge")
    assert response.status_code == 200
    assert response.json()["total"] == 0


async def test_list_knowledge_with_items(admin_client, test_tenant):
    for i in range(3):
        await admin_client.post(
            f"/api/v1/admin/{test_tenant.slug}/knowledge",
            json={"question": f"Q{i}?", "answer": f"A{i}"},
        )
    response = await admin_client.get(f"/api/v1/admin/{test_tenant.slug}/knowledge")
    assert response.status_code == 200
    assert response.json()["total"] == 3


async def test_list_knowledge_pagination(admin_client, test_tenant):
    for i in range(25):
        await admin_client.post(
            f"/api/v1/admin/{test_tenant.slug}/knowledge",
            json={"question": f"Q{i}?", "answer": f"A{i}"},
        )
    response = await admin_client.get(
        f"/api/v1/admin/{test_tenant.slug}/knowledge?page_size=10&page=2"
    )
    data = response.json()
    assert data["page"] == 2
    assert len(data["items"]) == 10


async def test_list_knowledge_search(admin_client, test_tenant):
    await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/knowledge",
        json={"question": "Return policy?", "answer": "7 days", "keywords": "return,refund"},
    )
    await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/knowledge",
        json={"question": "Shipping time?", "answer": "48 hours", "keywords": "shipping"},
    )
    response = await admin_client.get(f"/api/v1/admin/{test_tenant.slug}/knowledge?q=return")
    data = response.json()
    assert data["total"] == 1


async def test_get_knowledge(admin_client, test_tenant):
    r = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/knowledge",
        json={"question": "Sizing?", "answer": "See size chart"},
    )
    item_id = r.json()["id"]
    response = await admin_client.get(f"/api/v1/admin/{test_tenant.slug}/knowledge/{item_id}")
    assert response.status_code == 200
    assert response.json()["id"] == item_id


async def test_update_knowledge(admin_client, test_tenant):
    r = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/knowledge",
        json={"question": "Old?", "answer": "Old answer"},
    )
    item_id = r.json()["id"]
    response = await admin_client.put(
        f"/api/v1/admin/{test_tenant.slug}/knowledge/{item_id}",
        json={"answer": "New answer", "status": "draft"},
    )
    data = response.json()
    assert data["answer"] == "New answer"
    assert data["status"] == "draft"
    assert data["question"] == "Old?"  # unchanged


async def test_delete_knowledge_soft(admin_client, test_tenant):
    r = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/knowledge",
        json={"question": "Delete me?", "answer": "OK"},
    )
    item_id = r.json()["id"]
    resp = await admin_client.delete(f"/api/v1/admin/{test_tenant.slug}/knowledge/{item_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"
    get_resp = await admin_client.get(f"/api/v1/admin/{test_tenant.slug}/knowledge/{item_id}")
    assert get_resp.json()["status"] == "archived"


async def test_knowledge_requires_auth(client, test_tenant):
    response = await client.post(
        f"/api/v1/admin/{test_tenant.slug}/knowledge",
        json={"question": "x?", "answer": "x"},
    )
    assert response.status_code == 401


async def test_knowledge_tenant_isolation(admin_client, test_tenant, db):
    await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/knowledge",
        json={"question": "TenantA?", "answer": "TenantA"},
    )
    from app.schemas.knowledge import KnowledgeListParams
    from app.services.knowledge_service import list_knowledge

    items, total = list_knowledge(db, "other-random-id", KnowledgeListParams())
    assert total == 0


async def test_create_category(admin_client, test_tenant):
    response = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/categories",
        json={"name": "Returns", "description": "Return policies"},
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Returns"
