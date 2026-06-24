"""Streaming SSE endpoint tests.

Uses the fake embedding provider + in-memory DB from conftest,
so no real API calls are made.
"""

import json
from unittest import mock

import pytest


class FakeLLMResponse:
    """A mock LLM response that streams text token by token."""
    content: str
    tool_calls: list | None

    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


@pytest.fixture
def mock_graph():
    """Mock the compiled agent graph for streaming tests."""
    with mock.patch("app.services.chat_service._get_graph") as m:
        yield m


async def test_chitchat_streaming(client, test_tenant, mock_graph):
    """Simple greeting should return instantly via chitchat fast path, no agent call."""
    response = await client.get(
        f"/api/v1/{test_tenant.slug}/chat/stream",
        params={"session_id": "s1", "message": "你好"},
    )
    assert response.status_code == 200
    body = response.text
    assert "data: " in body, "SSE response should contain data events"
    # Parse SSE events
    events = _parse_sse(body)
    done = [e for e in events if e.get("type") == "done"]
    assert len(done) == 1
    assert done[0]["data"]["cache_hit"] == "L1"  # chitchat uses L1 tag
    assert "智能客服" in done[0]["data"]["answer"]
    # Agent graph was never called
    mock_graph.assert_not_called()


async def test_streaming_returns_sse_content_type(client, test_tenant):
    """Streaming endpoint returns text/event-stream content type."""
    response = await client.get(
        f"/api/v1/{test_tenant.slug}/chat/stream",
        params={"session_id": "s1", "message": "退货要几天"},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")


async def test_streaming_includes_request_id(client, test_tenant):
    """Streaming response includes X-Request-ID header."""
    response = await client.get(
        f"/api/v1/{test_tenant.slug}/chat/stream",
        params={"session_id": "s1", "message": "hello"},
    )
    assert response.status_code == 200
    assert "x-request-id" in response.headers


async def test_streaming_empty_message_rejected(client, test_tenant):
    """Empty message should return 422 validation error."""
    response = await client.get(
        f"/api/v1/{test_tenant.slug}/chat/stream",
        params={"session_id": "", "message": ""},
    )
    assert response.status_code == 422


async def test_streaming_no_message_param(client, test_tenant):
    """Missing message param should return 422."""
    response = await client.get(
        f"/api/v1/{test_tenant.slug}/chat/stream",
        params={"session_id": "s1"},
    )
    assert response.status_code == 422


async def test_streaming_nonexistent_tenant(client):
    """Non-existent tenant should return 404."""
    response = await client.get(
        "/api/v1/fake-tenant/chat/stream",
        params={"session_id": "s1", "message": "hello"},
    )
    assert response.status_code == 404


def _parse_sse(body: str) -> list[dict]:
    """Parse SSE text/event-stream body into list of event dicts."""
    events = []
    for block in body.split("\n\n"):
        for line in block.split("\n"):
            line = line.strip()
            if line.startswith("data: "):
                try:
                    events.append(json.loads(line[6:]))
                except json.JSONDecodeError:
                    pass
    return events
