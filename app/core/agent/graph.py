"""LangGraph agent graph — builds and compiles the ReAct agent.

Nodes: agent (LLM + tool definitions) → tools (ToolNode) → agent (loop)
The graph terminates when the LLM produces a response without tool_calls.
"""

import sqlite3

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_openai import ChatOpenAI

from app.config import settings
from app.core.agent.state import AgentState
from app.core.agent.tools import handoff_to_human, search_knowledge

_TOOLS = [search_knowledge, handoff_to_human]


def _build_llm() -> ChatOpenAI:
    """Create a ChatOpenAI instance bound with agent tools."""
    llm = ChatOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        temperature=0.1,
        max_tokens=800,
        max_retries=3,
        timeout=30.0,
    )
    return llm.bind_tools(_TOOLS)


def _should_continue(state: AgentState) -> str:
    """Route to tools node if the last AI message has tool_calls, else END."""
    messages = state["messages"]
    if not messages:
        return END
    last = messages[-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END


def build_agent_graph():
    """Build and return a compiled LangGraph agent with SQLite checkpointing.

    Returns a compiled graph.  Callers use ``graph.astream_events(...)``
    for SSE streaming or ``graph.ainvoke(...)`` for non-streaming execution.
    """
    llm = _build_llm()

    async def agent_node(state: AgentState):
        """Invoke LLM with tool definitions and full message history."""
        response = await llm.ainvoke(state["messages"])
        return {"messages": [response]}

    tool_node = ToolNode(_TOOLS)

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)

    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", _should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    # SQLite checkpoint for persistent conversation state.
    # SqliteSaver.from_conn_string is a context manager (LangGraph >=1.2),
    # so we create the sqlite3 connection ourselves to keep it alive.
    db_path = settings.database_url.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    return graph.compile(checkpointer=checkpointer)
