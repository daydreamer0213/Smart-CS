"""LLM client tests — mock DeepSeek API."""

import pytest
from unittest import mock
from openai import APITimeoutError, AuthenticationError
from pydantic import BaseModel, Field
from app.core.llm.client import LLMClient


class TestOutput(BaseModel):
    result: str = Field(description="test result")


async def test_chat_structured_parses_json():
    client = LLMClient(api_key="sk-test", base_url="https://test.api", model="test")
    mock_response = mock.AsyncMock()
    mock_response.choices = [
        mock.MagicMock(message=mock.MagicMock(parsed=TestOutput(result="hello")))
    ]
    client._client.beta.chat.completions.parse = mock.AsyncMock(return_value=mock_response)

    result = await client.chat_structured(
        [{"role": "user", "content": "test"}], TestOutput
    )
    assert result.result == "hello"


async def test_retry_on_timeout():
    client = LLMClient(api_key="sk-test", base_url="https://test.api", model="test")
    call_count = [0]

    async def flaky_chat(**kwargs):
        call_count[0] += 1
        if call_count[0] < 3:
            raise APITimeoutError("timeout")
        return mock.MagicMock(
            choices=[mock.MagicMock(message=mock.MagicMock(content="success"))]
        )

    client._client.chat.completions.create = flaky_chat

    result = await client.chat([{"role": "user", "content": "test"}])
    assert result == "success"
    assert call_count[0] == 3


async def test_no_retry_on_auth_error():
    client = LLMClient(api_key="sk-test", base_url="https://test.api", model="test")

    # Build a real httpx.Response so AuthenticationError can read .headers
    import httpx

    real_resp = httpx.Response(status_code=401, request=httpx.Request("POST", "https://test.api"))
    auth_err = AuthenticationError(
        "invalid key", response=real_resp, body={"error": {"message": "invalid key"}}
    )

    async def auth_fail(**kwargs):
        raise auth_err

    client._client.chat.completions.create = auth_fail

    with pytest.raises(AuthenticationError):
        await client.chat([{"role": "user", "content": "test"}])
