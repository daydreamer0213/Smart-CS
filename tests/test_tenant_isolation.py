"""Cross-tenant data isolation tests."""


async def test_knowledge_not_visible_across_tenants(admin_client, test_tenant, db):
    await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/knowledge",
        json={"question": "Secret FAQ", "answer": "Secret answer"},
    )

    from app.schemas.knowledge import KnowledgeListParams
    from app.services.knowledge_service import list_knowledge

    items, total = list_knowledge(db, "other-tenant-fake-id", KnowledgeListParams())
    assert total == 0
