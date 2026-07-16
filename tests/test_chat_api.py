"""Legacy chat route retirement tests."""


async def test_legacy_chat_route_is_not_mounted(client, test_tenant):
    """The old unauthenticated chat surface must not remain reachable."""
    response = await client.post(
        f"/api/v1/{test_tenant.slug}/chat",
        json={"session_id": "", "message": "test"},
    )
    assert response.status_code == 404
