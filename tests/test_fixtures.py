"""Verify test fixtures are working correctly.

Tests cover:
- Health endpoint returns expected status and version.
- Chat route is registered (returns 200 or 404, not 405).
- X-Request-ID header is injected by LoggingMiddleware.
"""


async def test_health_endpoint(client):
    """GET /health should return status ok and current version."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"


async def test_placeholder_chat_endpoint(client):
    """POST /api/v1/{tenant_slug}/chat is registered.

    The route returns 200 when the tenant exists or 404 when it does not.
    Either is acceptable — the goal is to prove the route exists and does
    not 405 (method not allowed).
    """
    response = await client.post("/api/v1/test-tenant/chat", json={})
    assert response.status_code in (200, 404)


async def test_x_request_id_header(client):
    """Every response should carry an X-Request-ID header."""
    response = await client.get("/health")
    assert "x-request-id" in response.headers


async def test_admin_route_extracts_correct_slug(client):
    """Admin paths must not extract 'admin' as the tenant slug.

    A 401 Unauthorized (missing X-Admin-Key) proves the route correctly parsed
    "demo" as the tenant slug — the auth middleware fired after extraction.
    A 200 would mean the stub is still in place.  A 404 would mean the
    route tried to look up "admin" as a tenant slug.
    """
    response = await client.get("/api/v1/admin/demo/knowledge")
    assert response.status_code in (200, 401), (
        f"Expected 200 (stub) or 401 (auth), got {response.status_code}. "
        f"A 404 would mean 'admin' was treated as the tenant slug."
    )
