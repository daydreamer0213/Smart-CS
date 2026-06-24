"""ChromaDB vector store with per-tenant collection isolation."""

import chromadb
from chromadb.config import Settings as ChromaSettings


class VectorStore:
    def __init__(self, persist_dir: str):
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    def _coll_name(self, tenant_slug: str) -> str:
        return f"{tenant_slug}_knowledge"

    def get_collection(self, tenant_slug: str):
        return self._client.get_or_create_collection(
            name=self._coll_name(tenant_slug),
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, tenant_slug: str, doc_id: str, embedding: list[float], metadata: dict) -> None:
        coll = self.get_collection(tenant_slug)
        coll.add(ids=[doc_id], embeddings=[embedding], metadatas=[metadata])

    def update(self, tenant_slug: str, doc_id: str, embedding: list[float], metadata: dict) -> None:
        coll = self.get_collection(tenant_slug)
        coll.update(ids=[doc_id], embeddings=[embedding], metadatas=[metadata])

    def delete(self, tenant_slug: str, doc_id: str) -> None:
        coll = self.get_collection(tenant_slug)
        try:
            coll.delete(ids=[doc_id])
        except Exception:
            pass

    def search(
        self, tenant_slug: str, query_embedding: list[float], top_k: int = 5
    ) -> list[tuple[str, float]]:
        coll = self.get_collection(tenant_slug)
        if coll.count() == 0:
            return []
        n = min(top_k, coll.count())
        results = coll.query(query_embeddings=[query_embedding], n_results=n)
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        return list(zip(ids, distances))
