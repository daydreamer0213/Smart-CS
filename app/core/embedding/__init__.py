"""Embedding provider factory."""

from app.config import Settings
from app.core.embedding.base import BaseEmbeddingProvider
from app.core.embedding.hash_provider import HashEmbeddingProvider
from app.core.embedding.openai_provider import OpenAIEmbeddingProvider


def get_embedding_provider(settings: Settings) -> BaseEmbeddingProvider:
    if settings.embedding_provider == "hash":
        return HashEmbeddingProvider()
    if settings.embedding_provider == "bge":
        from app.core.embedding.bge_provider import BGEBembeddingProvider  # lazy import
        return BGEBembeddingProvider(model_name=settings.embedding_model)
    return OpenAIEmbeddingProvider(
        api_key=settings.embedding_api_key or settings.llm_api_key,
        model=settings.embedding_model,
        base_url=settings.embedding_base_url or None,
    )
