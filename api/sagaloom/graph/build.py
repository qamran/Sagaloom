"""Builds the Sagaloom graph (R18.1):

START -> guard -> (safe / off) router -> agent | (blocked) END
agent -> (tool calls) tools -> (queued preferences) remember -> check | agent
tools -> (unchecked/undecided proposal) check -> approval_gate
approval_gate -> check (edit / save as myth) | commit;  commit -> agent;  agent -> END.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

from sagaloom import models as sagaloom_models
from sagaloom.config import Settings
from sagaloom.graph.nodes import (
    ModelFor,
    RoleModel,
    approval_gate,
    make_agent_node,
    make_check_node,
    make_commit_node,
    make_guard_node,
    make_remember_node,
    make_router_node,
    make_tools_node,
    route_after_guard,
    route_after_agent,
    route_after_remember,
    route_after_tools,
)
from sagaloom.graph.state import SagaState
from sagaloom.settings_store import DevSettings
from sagaloom.tools.canon_tools import make_tools
from sagaloom.wiki.client import WikiClient

RECURSION_LIMIT = 25


def build_graph(
    *,
    store,
    model_for: ModelFor,
    checkpointer,
    dev: Callable[[], DevSettings] = DevSettings,
    wiki: WikiClient | None = None,
    memory_store: BaseStore | None = None,
) -> CompiledStateGraph:
    """`memory_store` holds the author preferences (R10.2); the app passes its AsyncSqliteStore,
    tests an InMemoryStore (the default)."""
    if memory_store is None:
        memory_store = InMemoryStore()
    tools = make_tools(
        store, RoleModel(model_for, "extractor"), RoleModel(model_for, "judge"), wiki=wiki
    )
    g = StateGraph(SagaState)
    g.add_node("guard", make_guard_node(model_for, dev))
    g.add_node("router", make_router_node(model_for))
    g.add_node("agent", make_agent_node(model_for, tools, dev, memory_store))
    g.add_node("tools", make_tools_node(tools, dev))
    g.add_node("remember", make_remember_node(memory_store))
    g.add_node("check", make_check_node(store, model_for))
    g.add_node("approval_gate", approval_gate, destinations=("check", "commit"))
    g.add_node("commit", make_commit_node(store))

    g.add_edge(START, "guard")
    g.add_conditional_edges("guard", route_after_guard, {"router": "router", END: END})
    g.add_edge("router", "agent")
    g.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
    g.add_conditional_edges(
        "tools", route_after_tools, {"remember": "remember", "check": "check", "agent": "agent"}
    )
    g.add_conditional_edges("remember", route_after_remember, {"check": "check", "agent": "agent"})
    g.add_edge("check", "approval_gate")
    g.add_edge("commit", "agent")
    return g.compile(checkpointer=checkpointer, store=memory_store)


def run_config(thread_id: str, world_id: str) -> dict:
    """Config for every run; the metadata groups LangSmith runs into one thread (R15.1)."""
    return {
        "configurable": {"thread_id": thread_id},
        "metadata": {"thread_id": thread_id, "world_id": world_id},
        "recursion_limit": RECURSION_LIMIT,
    }


def checkpoint_serde() -> JsonPlusSerializer:
    """Strict msgpack (R15): only LangGraph's built-in safe types plus our own
    `sagaloom.models` classes may be rebuilt from a checkpoint. The default is permissive (it
    warns on every unknown type); an explicit `allowed_msgpack_modules` list is the supported
    way to lock it down, so no env var is needed."""
    return JsonPlusSerializer(
        allowed_msgpack_modules=[
            ("sagaloom.models", name)
            for name in vars(sagaloom_models)
            if isinstance(getattr(sagaloom_models, name), type)
            and getattr(sagaloom_models, name).__module__ == sagaloom_models.__name__
        ]
    )


@asynccontextmanager
async def sqlite_checkpointer(settings: Settings) -> AsyncIterator[AsyncSqliteSaver]:
    """The restart-safe checkpointer (R18.7), with the strict serde above."""
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(Path(settings.data_dir) / "checkpoints.sqlite")) as conn:
        yield AsyncSqliteSaver(conn, serde=checkpoint_serde())
