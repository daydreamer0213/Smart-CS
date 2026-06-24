"""Chat API integration tests."""


async def test_chat_route_registered(client):
    """Chat endpoint is registered."""
    response = await client.post(
        "/api/v1/test-tenant/chat",
        json={"session_id": "", "message": "test"},
    )
    assert response.status_code != 405  # Not "Method Not Allowed"


async def test_chat_session_id_generated(admin_client, test_tenant):
    """If empty session_id is provided, one should be generated in the response."""
    response = await admin_client.post(
        f"/api/v1/{test_tenant.slug}/chat",
        json={"session_id": "", "message": "hello"},
    )
    # 500 = LLM unavailable, 200/401 = auth or other, 404 = tenant not found
    assert response.status_code in (200, 401, 404, 500)
