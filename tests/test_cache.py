"""Cache tests: L1 exact + L2 semantic."""

import time

from app.core.cache.exact import ExactCache
from app.core.cache.semantic import SemanticCache


class TestExactCache:
    def test_get_set(self):
        c = ExactCache()
        c.set("t1", "question?", "answer!")
        assert c.get("t1", "question?") == "answer!"

    def test_miss(self):
        c = ExactCache()
        assert c.get("t1", "nope") is None

    def test_ttl_expiry(self):
        c = ExactCache()
        c.set("t1", "q?", "a!", ttl=0)  # expired immediately
        assert c.get("t1", "q?") is None

    def test_invalidate_tenant(self):
        c = ExactCache()
        c.set("t1", "q1", "a1")
        c.set("t2", "q2", "a2")
        c.invalidate("t1")
        assert c.get("t1", "q1") is None
        assert c.get("t2", "q2") == "a2"


class TestSemanticCache:
    def test_exact_match(self):
        c = SemanticCache()
        c.set("t1", [1.0, 0.0], "answer")
        assert c.get("t1", [1.0, 0.0]) == "answer"

    def test_close_match(self):
        c = SemanticCache()
        c.set("t1", [1.0, 0.0], "answer")
        assert c.get("t1", [0.99, 0.01]) is not None

    def test_below_threshold(self):
        c = SemanticCache()
        c.set("t1", [1.0, 0.0], "answer")
        assert c.get("t1", [0.0, 1.0]) is None  # orthogonal

    def test_invalidate(self):
        c = SemanticCache()
        c.set("t1", [1.0, 0.0], "answer")
        c.invalidate("t1")
        assert c.get("t1", [1.0, 0.0]) is None
