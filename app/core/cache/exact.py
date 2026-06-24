"""L1 exact-match cache — per-tenant, TTL-based."""

import time


class ExactCache:
    def __init__(self):
        self._store: dict[str, tuple[float, str]] = {}

    def _key(self, tenant_id: str, question: str) -> str:
        return f"{tenant_id}:{question.strip().lower()}"

    def get(self, tenant_id: str, question: str) -> str | None:
        entry = self._store.get(self._key(tenant_id, question))
        if entry and time.time() < entry[0]:
            return entry[1]
        return None

    def set(self, tenant_id: str, question: str, answer: str, ttl: int = 300):
        self._store[self._key(tenant_id, question)] = (time.time() + ttl, answer)

    def invalidate(self, tenant_id: str):
        prefix = f"{tenant_id}:"
        keys = [k for k in self._store if k.startswith(prefix)]
        for k in keys:
            del self._store[k]
