# tests/test_agent.py
"""Agent graph integration tests — uses mock LLM to avoid real API calls."""

import json
from unittest import mock

import pytest


class TestAgentGraph:
    """Test the agent graph structure and routing logic."""

    def test_graph_builds_without_error(self):
        """Graph compiles successfully with dummy API key."""
        from app.config import settings
        old_key = settings.llm_api_key
        settings.llm_api_key = "sk-test-dummy"
        try:
            from app.core.agent.graph import build_agent_graph
            graph = build_agent_graph()
            assert graph is not None
        finally:
            settings.llm_api_key = old_key

    def test_should_continue_without_messages(self):
        """Empty state routes to END."""
        from app.core.agent.graph import _should_continue
        result = _should_continue({"messages": []})
        assert result == "__end__"

    def test_should_continue_with_text_only(self):
        """State with text-only AI message routes to END."""
        from app.core.agent.graph import _should_continue
        from langchain_core.messages import AIMessage
        state = {"messages": [AIMessage(content="Hello!")]}
        result = _should_continue(state)
        assert result == "__end__"

    def test_should_continue_with_tool_calls(self):
        """State with tool_call AI message routes to tools."""
        from app.core.agent.graph import _should_continue
        from langchain_core.messages import AIMessage
        msg = AIMessage(content="", tool_calls=[{"name": "search_knowledge", "args": {"query": "test"}, "id": "call_1"}])
        state = {"messages": [msg]}
        result = _should_continue(state)
        assert result == "tools"


class TestAgentState:
    """Test AgentState TypedDict structure."""

    def test_state_keys(self):
        from app.core.agent.state import AgentState
        # MessagesState provides 'messages', we add tenant_id, session_id, handoff
        keys = list(AgentState.__annotations__.keys())
        assert "messages" in keys
        assert "tenant_id" in keys
        assert "session_id" in keys
        assert "handoff" in keys


class TestAgentSystemPrompt:
    """Test system prompt building."""

    def test_build_agent_prompt(self):
        from app.core.llm.prompts import build_agent_system_prompt
        prompt = build_agent_system_prompt("TestStore", "本店7天退货")
        assert "TestStore" in prompt
        assert "本店7天退货" in prompt
        assert "search_knowledge" in prompt
        assert "handoff_to_human" in prompt

    def test_build_agent_prompt_no_append(self):
        from app.core.llm.prompts import build_agent_system_prompt
        prompt = build_agent_system_prompt("TestStore")
        assert "TestStore" in prompt
        assert "商户专属说明" not in prompt
