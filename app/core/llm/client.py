"""LLM client with retry and structured output."""

import asyncio
import time

import structlog
from openai import APIError, APITimeoutError, AsyncOpenAI, RateLimitError
from pydantic import BaseModel

logger = structlog.get_logger()

RETRYABLE = (APITimeoutError, RateLimitError)


class LLMClient:
    def __init__(self, api_key: str, base_url: str, model: str):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=30.0)
        self._model = model
        self._max_retries = 3

    async def chat(
        self, messages: list[dict], temperature: float = 0.1, max_tokens: int = 1000
    ) -> str:
        for attempt in range(self._max_retries):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content or ""
            except RETRYABLE as e:
                wait = 2 ** attempt
                logger.warning("llm_retry", attempt=attempt + 1, wait=wait, error=str(e))
                if attempt == self._max_retries - 1:
                    raise
                await asyncio.sleep(wait)
            except Exception:
                raise

    async def chat_structured(
        self, messages: list[dict], output_class: type[BaseModel]
    ) -> BaseModel:
        completion = await self._client.beta.chat.completions.parse(
            model=self._model,
            messages=messages,
            response_format=output_class,
            temperature=0.0,
        )
        result = completion.choices[0].message.parsed
        if result is None:
            content = completion.choices[0].message.content or "{}"
            return output_class.model_validate_json(content)
        return result

    async def chat_stream(
        self, messages: list[dict], temperature: float = 0.1, max_tokens: int = 1000
    ):
        """Stream chat tokens. Yields content deltas as they arrive."""
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
