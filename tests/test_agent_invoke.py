"""Agent invocation tests — graph.ainvoke and graph.astream_events.

Uses fake embedding provider from conftest.  LLM is mocked to avoid
real API calls.
"""

import json
from unittest import mock

import pytest
from langchain_core.messages import AIMessage

from app.core.agent.graph import build_agent_graph
from app.core.agent.tools import set_runtime


@pytest.fixture
def mock_llm():
    """Mock ChatOpenAI to return controlled responses."""
    with mock.patch("app.core.agent.graph.ChatOpenAI") as m:
        mock_instance = mock.MagicMock()
        m.return_value = mock_instance
        mock_instance.bind_tools.return_value = mock_instance
        mock_instance.ainvoke = mock.AsyncMock()
        mock_instance.astream = mock.AsyncMock()
        yield mock_instance


async def test_agent_direct_reply_no_tools(mock_llm, db, test_tenant):
    """Agent responds directly without tool calls for simple queries."""
    mock_llm.ainvoke.return_value = AIMessage(content="您好！有什么可以帮助您的？")

    set_runtime(test_tenant.slug, db)
    graph = build_agent_graph()
    state = await graph.ainvoke(
        {
            "messages": [
                {"role": "system", "content": "你是客服，简单问候直接回复。"},
                {"role": "user", "content": "你好"},
            ],
            "tenant_id": test_tenant.id,
            "session_id": "test-session",
            "handoff": False,
        },
        {"configurable": {"thread_id": "test-thread"}},
    )
    msgs = state["messages"]
    assert len(msgs) >= 2
    last = msgs[-1]
    assert last.content
    assert "你好" in last.content.lower() or "帮助" in last.content or "什么" in last.content


async def test_agent_calls_search_knowledge_tool(mock_llm, db, test_tenant):
    """Agent calls search_knowledge when a product question is asked.

    First LLM call returns tool_calls, second returns final answer.
    """
    # First call: tool invocation
    # Second call: final response
    mock_llm.ainvoke.side_effect = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "search_knowledge", "args": {"query": "退货政策"}, "id": "call_1"}
            ],
        ),
        AIMessage(content="根据我们的退货政策，您可以在7天内无理由退货。"),
    ]

    set_runtime(test_tenant.slug, db)
    graph = build_agent_graph()
    state = await graph.ainvoke(
        {
            "messages": [
                {"role": "system", "content": "你是客服，用工具查知识库。"},
                {"role": "user", "content": "退货政策是什么"},
            ],
            "tenant_id": test_tenant.id,
            "session_id": "test-session",
            "handoff": False,
        },
        {"configurable": {"thread_id": "test-thread-2"}},
    )
    msgs = state["messages"]
    # Should have: system, user, AI(tool_calls), Tool(tool_result), AI(final_answer)
    assert len(msgs) >= 5
    tool_msgs = [m for m in msgs if m.type == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].name == "search_knowledge"


async def test_agent_calls_handoff_tool(mock_llm, db, test_tenant):
    """Agent calls handoff_to_human for complaints."""
    mock_llm.ainvoke.side_effect = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "handoff_to_human", "args": {"reason": "用户投诉"}, "id": "call_h"}
            ],
        ),
        AIMessage(content="已为您转接人工客服。"),
    ]

    set_runtime(test_tenant.slug, db)
    graph = build_agent_graph()
    state = await graph.ainvoke(
        {
            "messages": [
                {"role": "system", "content": "你是客服，投诉转人工。"},
                {"role": "user", "content": "我要投诉，你们太差了"},
            ],
            "tenant_id": test_tenant.id,
            "session_id": "test-session",
            "handoff": False,
        },
        {"configurable": {"thread_id": "test-thread-3"}},
    )
    msgs = state["messages"]
    tool_msgs = [m for m in msgs if m.type == "tool"]
    assert any(m.name == "handoff_to_human" for m in tool_msgs)


async def test_tool_loop_error_then_retry(mock_llm, db, test_tenant):
    """Agent handles an empty search result and still responds."""
    mock_llm.ainvoke.side_effect = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "search_knowledge", "args": {"query": "火星旅行"}, "id": "call_e"}
            ],
        ),
        AIMessage(content="抱歉，暂时无法回答您关于火星旅行的问题，是否需要转人工？"),
    ]

    set_runtime(test_tenant.slug, db)
    graph = build_agent_graph()
    state = await graph.ainvoke(
        {
            "messages": [
                {"role": "system", "content": "你是客服。"},
                {"role": "user", "content": "火星旅行怎么去"},
            ],
            "tenant_id": test_tenant.id,
            "session_id": "test-session",
            "handoff": False,
        },
        {"configurable": {"thread_id": "test-thread-4"}},
    )
    msgs = state["messages"]
    answers = [m for m in msgs if m.type == "ai" and m.content and not m.tool_calls]
    assert len(answers) >= 1
    assert "抱歉" in answers[-1].content or "无法回答" in answers[-1].content
