"""Admin analytics API tests."""

import pytest


async def test_analytics_overview_endpoint(admin_client, test_tenant):
    """GET overview returns 200 with all expected fields."""
    response = await admin_client.get(
        f"/api/v1/admin/{test_tenant.slug}/analytics/overview"
    )
    assert response.status_code == 200
    data = response.json()
    assert "total_conversations" in data
    assert "avg_latency_ms" in data
    assert "cache_hit_rate" in data
    assert "handoff_rate" in data


async def test_analytics_intents_endpoint(admin_client, test_tenant):
    """GET intents returns 200 with list."""
    response = await admin_client.get(
        f"/api/v1/admin/{test_tenant.slug}/analytics/intents"
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


async def test_analytics_daily_endpoint(admin_client, test_tenant):
    """GET daily returns 200 with list."""
    response = await admin_client.get(
        f"/api/v1/admin/{test_tenant.slug}/analytics/daily"
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


async def test_analytics_knowledge_endpoint(admin_client, test_tenant):
    """GET knowledge returns 200 with list."""
    response = await admin_client.get(
        f"/api/v1/admin/{test_tenant.slug}/analytics/knowledge"
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


async def test_analytics_requires_auth(client, test_tenant):
    """Analytics endpoints require X-Admin-Key header."""
    response = await client.get(
        f"/api/v1/admin/{test_tenant.slug}/analytics/overview"
    )
    assert response.status_code == 401


async def test_analytics_respects_days_param(admin_client, test_tenant):
    """Analytics accepts a custom days parameter."""
    response = await admin_client.get(
        f"/api/v1/admin/{test_tenant.slug}/analytics/overview?days=30"
    )
    assert response.status_code == 200
    data = response.json()
    assert "total_conversations" in data
