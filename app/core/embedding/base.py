"""Embedding provider abstract base class."""

from abc import ABC, abstractmethod


class BaseEmbeddingProvider(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for a batch of texts."""

    @property
    @abstractmethod
    def dim(self) -> int:
        """Return embedding vector dimension."""
