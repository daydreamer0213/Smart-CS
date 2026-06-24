"""BGE local embedding provider via sentence-transformers."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from app.core.embedding.base import BaseEmbeddingProvider

_executor = ThreadPoolExecutor(max_workers=1)


class BGEBembeddingProvider(BaseEmbeddingProvider):
    def __init__(self, model_name: str = "BAAI/bge-large-zh-v1.5"):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_name)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        loop = asyncio.get_running_loop()
        embeddings = await loop.run_in_executor(
            _executor, self._model.encode, texts, True
        )
        return [e.tolist() for e in embeddings]

    @property
    def dim(self) -> int:
        return 1024
