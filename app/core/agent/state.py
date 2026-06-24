"""Agent state definition using LangGraph MessagesState.

MessagesState provides a built-in ``messages`` key with the ``add_messages``
reducer, which merges new AI/Tool/Human messages into the history list
automatically.  We extend it with tenant/session metadata for tool access
and persistence.
"""

from typing import TypedDict

from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """Extended messages state carrying tenant and session context."""
    tenant_id: str       # UUID of the current tenant
    session_id: str      # client-supplied session UUID
    handoff: bool        # set to True when handoff_to_human tool is called
