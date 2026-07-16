"""Primary assistant route smoke tests."""


async def test_assistant_requires_jwt(client, test_tenant):
    response = await client.post(
        f"/api/v1/{test_tenant.slug}/assistant/chat",
        json={"session_id": "test-session", "message": "hello"},
    )
    assert response.status_code == 401
