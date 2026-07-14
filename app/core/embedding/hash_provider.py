"""Deterministic local embedding provider for demos and tests."""

import hashlib
import math

from app.core.embedding.base import BaseEmbeddingProvider


class HashEmbeddingProvider(BaseEmbeddingProvider):
    def __init__(self, dim: int = 64):
        self._dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        values = []
        seed = text.encode("utf-8")
        counter = 0
        while len(values) < self._dim:
            digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            values.extend((byte / 127.5) - 1.0 for byte in digest)
            counter += 1
        vector = values[: self._dim]
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    @property
    def dim(self) -> int:
        return self._dim
