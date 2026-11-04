"""Builds the Sagaloom graph (R18.1):

START -> agent -> (tool calls) tools -> (unchecked/undecided proposal) check -> approval_gate
approval_gate -> check (edit / save as myth) | commit;  commit -> agent;  agent -> END.
"""

from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from sagaloom.config import Settings
from sagaloom.graph.nodes import (
    ModelFor,
    RoleModel,
    approval_gate,
    make_agent_node,
    make_check_node,
    make_commit_node,
    route_after_agent,
    route_after_tools,
)
from sagaloom.graph.state import SagaState
from sagaloom.tools.canon_tools import make_tools

RECURSION_LIMIT = 25


def build_graph(*, store, model_for: ModelFor, checkpointer, settings: Settings) -> CompiledStateGraph:
    tools = make_tools(store, RoleModel(model_for, "extractor"), RoleModel(model_for, "judge"))
    g = StateGraph(SagaState)
    g.add_node("agent", make_agent_node(model_for, tools, settings))
    g.add_node("tools", ToolNode(tools, handle_tool_errors=True))
    g.add_node("check", make_check_node(store, model_for))
    g.add_node("approval_gate", approval_gate, destinations=("check", "commit"))
    g.add_node("commit", make_commit_node(store))

    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
    g.add_conditional_edges("tools", route_after_tools, {"check": "check", "agent": "agent"})
    g.add_edge("check", "approval_gate")
    g.add_edge("commit", "agent")
    return g.compile(checkpointer=checkpointer)


def run_config(thread_id: str, world_id: str) -> dict:
    """Config for every run; the metadata groups LangSmith runs into one thread (R15.1)."""
    return {
        "configurable": {"thread_id": thread_id},
        "metadata": {"thread_id": thread_id, "world_id": world_id},
        "recursion_limit": RECURSION_LIMIT,
    }


def sqlite_checkpointer(settings: Settings):
    """Async context manager for the restart-safe checkpointer (R18.7)."""
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    return AsyncSqliteSaver.from_conn_string(str(Path(settings.data_dir) / "checkpoints.sqlite"))
