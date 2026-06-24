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


class TestHandoffToHuman:
    """Test the handoff_to_human tool."""

    def test_tool_has_name(self):
        from app.core.agent.tools import handoff_to_human
        assert handoff_to_human.name == "handoff_to_human"

    def test_tool_accepts_reason_arg(self):
        from app.core.agent.tools import handoff_to_human
        schema = handoff_to_human.args_schema.model_json_schema()
        assert "reason" in schema.get("properties", {})
