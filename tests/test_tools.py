# tests/test_tools.py
"""Unit tests for agent tools."""

import json
import pytest


class TestSearchKnowledge:
    """Test the search_knowledge tool function signature and structure."""

    def test_tool_has_name(self):
        from app.core.agent.tools import search_knowledge
        assert search_knowledge.name == "search_knowledge"

    def test_tool_has_description(self):
        from app.core.agent.tools import search_knowledge
        assert len(search_knowledge.description) > 20

    def test_tool_accepts_query_arg(self):
        from app.core.agent.tools import search_knowledge
        # Check that the tool schema includes 'query' as a parameter
        schema = search_knowledge.args_schema.model_json_schema()
        assert "query" in schema.get("properties", {})

    async def test_retrieval_exception_is_unavailable_without_exception_text(self, monkeypatch):
        from app.core.agent.tools import search_knowledge, set_runtime

        def fail_vector_store():
            raise RuntimeError("secret retrieval failure")

        monkeypatch.setattr("app.core.agent.tools.get_vector_store", fail_vector_store)
        set_runtime("tenant", object(), role="employee", tenant_id="tenant-id")

        raw = await search_knowledge.ainvoke({"query": "leave policy"})
        payload = json.loads(raw)

        assert payload == {"status": "UNAVAILABLE", "results": []}
        assert "secret retrieval failure" not in raw

    async def test_missing_tenant_context_is_unavailable(self, monkeypatch):
        from app.core.agent.tools import search_knowledge, set_runtime

        class FakeEmbedding:
            async def embed(self, _texts):
                return [[0.0]]

        class FakeRetriever:
            def search(self, *_args):
                return []

        monkeypatch.setattr("app.core.agent.tools.get_embedding_provider", lambda: FakeEmbedding())
        monkeypatch.setattr("app.core.agent.tools.get_vector_store", lambda: FakeRetriever())
        monkeypatch.setattr("app.core.agent.tools.get_bm25_manager", lambda: FakeRetriever())
        set_runtime("tenant", object(), role="employee", tenant_id=None)

        payload = json.loads(await search_knowledge.ainvoke({"query": "leave policy"}))

        assert payload == {"status": "UNAVAILABLE", "results": []}


class TestHandoffToHuman:
    """Test the handoff_to_human tool."""

    def test_tool_has_name(self):
        from app.core.agent.tools import handoff_to_human
        assert handoff_to_human.name == "handoff_to_human"

    def test_tool_accepts_reason_arg(self):
        from app.core.agent.tools import handoff_to_human
        schema = handoff_to_human.args_schema.model_json_schema()
        assert "reason" in schema.get("properties", {})
