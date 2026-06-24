"""Verify test fixtures are working correctly."""


async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"


async def test_placeholder_chat_endpoint(client):
    response = await client.post("/api/v1/test-tenant/chat", json={})
    assert response.status_code in (200, 404)


async def test_x_request_id_header(client):
    response = await client.get("/health")
    assert "x-request-id" in response.headers


async def test_admin_route_extracts_correct_slug(client, test_tenant):
    response = await client.get(f"/api/v1/admin/{test_tenant.slug}/knowledge")
    assert response.status_code == 401, (
        f"Expected 401 (auth required), got {response.status_code}"
    )
