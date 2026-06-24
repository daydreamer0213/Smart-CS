"""Embedding provider factory."""

from app.config import Settings
from app.core.embedding.base import BaseEmbeddingProvider
from app.core.embedding.openai_provider import OpenAIEmbeddingProvider
from app.core.embedding.bge_provider import BGEBembeddingProvider


def get_embedding_provider(settings: Settings) -> BaseEmbeddingProvider:
    if settings.embedding_provider == "bge":
        return BGEBembeddingProvider(model_name=settings.embedding_model)
    return OpenAIEmbeddingProvider(
        api_key=settings.embedding_api_key or settings.llm_api_key,
        model=settings.embedding_model,
        base_url=settings.embedding_base_url or None,
    )
