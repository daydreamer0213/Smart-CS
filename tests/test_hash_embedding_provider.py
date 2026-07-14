"""Tests for deterministic local demo embeddings."""

from app.core.embedding.hash_provider import HashEmbeddingProvider


async def test_hash_embedding_provider_is_deterministic():
    provider = HashEmbeddingProvider(dim=8)

    first = (await provider.embed(["hello"]))[0]
    second = (await provider.embed(["hello"]))[0]

    assert first == second
    assert len(first) == 8
    assert provider.dim == 8
