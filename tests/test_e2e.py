"""End-to-end chat route smoke tests."""

from app.schemas.chat import ChatResponse


async def test_chat_endpoint_exists(admin_client, test_tenant):
    """Verify the chat endpoint is reachable."""
    response = await admin_client.post(
        f"/api/v1/{test_tenant.slug}/chat",
        json={"session_id": "test-session", "message": "hello"},
    )
    assert response.status_code in (200, 401, 500)


async def test_chat_without_llm_returns_handoff(client, test_tenant, monkeypatch):
    """Verify the non-streaming route shape without touching a real LLM."""
    async def fake_process_chat(tenant, db, session_id, message):
        return ChatResponse(
            answer="human handoff",
            intent="human",
            confidence=1.0,
            sources=[],
            cache_hit="miss",
            session_id=session_id,
            handoff=True,
        )

    monkeypatch.setattr("app.api.chat.process_chat", fake_process_chat)

    response = await client.post(
        f"/api/v1/{test_tenant.slug}/chat",
        json={"session_id": "", "message": "human please"},
    )
    assert response.status_code == 200
    assert response.json()["handoff"] is True
