"""JSON + SSE endpoints (R19.1). Everything here is mounted behind the shared-secret check."""

import asyncio
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from sagaloom.graph.build import run_config
from sagaloom.models import Decision, Entry, Usage, World
from sagaloom.promptlog import PromptLogHandler, PromptRecord
from sagaloom.tools.canon_tools import make_tools
from sagaloom.web.sse import run_turn_events, sse_response

router = APIRouter()


class NewWorld(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class NewThread(BaseModel):
    world_id: str


class NewMessage(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class DecisionBody(BaseModel):
    decisions: list[Decision]


def _deps(request: Request):
    return request.app.state.deps


def _thread(request: Request, thread_id: str):
    info = _deps(request).threads.get(thread_id)
    if info is None:
        raise HTTPException(status_code=404, detail="thread not found")
    return info


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return str(content)


def message_dict(m: BaseMessage) -> dict:
    """{role, content, name?, tool_calls?}; `review` is the author's decision note (R18.6)."""
    out: dict[str, Any] = {"content": _text(m.content)}
    if isinstance(m, HumanMessage):
        out = {"role": "review" if m.name == "review" else "user", **out}
        if m.name:
            out["name"] = m.name
    elif isinstance(m, AIMessage):
        out = {"role": "assistant", **out}
        if m.tool_calls:
            out["tool_calls"] = [
                {"id": c.get("id"), "name": c["name"], "args": c["args"]} for c in m.tool_calls
            ]
    elif isinstance(m, ToolMessage):
        out = {"role": "tool", **out}
        if m.name:
            out["name"] = m.name
    else:
        out = {"role": m.type, **out}
    return out


def _pending(state) -> dict | None:
    return dict(state.interrupts[0].value) if state.interrupts else None


def _turn_config(request: Request, thread, emit: Callable[[str, dict], None]) -> dict:
    d = _deps(request)
    s = d.settings
    secrets = [s.openrouter_api_key.get_secret_value(), s.api_shared_secret.get_secret_value()]
    if s.gemini_api_key:
        secrets.append(s.gemini_api_key)
    cfg = run_config(thread.thread_id, thread.world_id)
    cfg["callbacks"] = [
        PromptLogHandler(d.promptlog, thread.thread_id, emit, settings=s, secrets=secrets)
    ]
    return cfg


def _stream_run(request: Request, thread, input_or_command: Any):
    queue: asyncio.Queue = asyncio.Queue()
    cfg = _turn_config(request, thread, lambda name, data: queue.put_nowait({"event": name, "data": data}))
    return sse_response(run_turn_events(_deps(request).graph, input_or_command, cfg, extra=queue))


# ---------- worlds and entries ----------


@router.get("/worlds")
def list_worlds(request: Request) -> list[World]:
    return _deps(request).worlds.list()


@router.post("/worlds")
def create_world(body: NewWorld, request: Request) -> World:
    return _deps(request).worlds.create(body.name.strip() or "World")


@router.get("/worlds/{world_id}/entries")
def list_entries(world_id: str, request: Request) -> list[Entry]:
    return _deps(request).store.list_entries(world_id)


@router.get("/worlds/{world_id}/entries/{entry_id}")
def get_entry(world_id: str, entry_id: str, request: Request) -> Entry:
    entry = _deps(request).store.get_entry(world_id, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="entry not found")
    return entry


# ---------- threads ----------


@router.post("/threads")
def create_thread(body: NewThread, request: Request) -> dict:
    d = _deps(request)
    if d.worlds.get(body.world_id) is None:
        raise HTTPException(status_code=404, detail="world not found")
    return {"thread_id": d.threads.create(body.world_id)}


@router.get("/threads")
async def list_threads(request: Request, pending: bool = False) -> list[dict]:
    d = _deps(request)
    out = []
    for t in d.threads.list():
        state = await d.graph.aget_state({"configurable": {"thread_id": t.thread_id}})
        interrupt = _pending(state)
        count = len(interrupt["proposals"]) if interrupt else 0
        if pending and not count:
            continue
        out.append({"thread_id": t.thread_id, "world_id": t.world_id, "pending": count})
    return out


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str, request: Request) -> dict:
    t = _thread(request, thread_id)
    state = await _deps(request).graph.aget_state({"configurable": {"thread_id": thread_id}})
    values = state.values or {}
    interrupt = _pending(state)
    return {
        "thread_id": thread_id,
        "world_id": t.world_id,
        "messages": [message_dict(m) for m in values.get("messages") or []],
        "pending_interrupt": (
            {"proposals": interrupt["proposals"], "checks": interrupt["checks"],
             **({"error": interrupt["error"]} if interrupt.get("error") else {})}
            if interrupt
            else None
        ),
        "usage": (values.get("token_usage") or Usage()).model_dump(),
    }


@router.post("/threads/{thread_id}/messages")
async def post_message(thread_id: str, body: NewMessage, request: Request):
    t = _thread(request, thread_id)
    state = await _deps(request).graph.aget_state({"configurable": {"thread_id": thread_id}})
    if state.interrupts:  # a new message would silently drop the pending approval (R15)
        raise HTTPException(status_code=409, detail="approval pending")
    return _stream_run(
        request, t, {"messages": [HumanMessage(content=body.content)], "world_id": t.world_id}
    )


@router.post("/threads/{thread_id}/decisions")
async def post_decisions(thread_id: str, body: DecisionBody, request: Request):
    t = _thread(request, thread_id)
    state = await _deps(request).graph.aget_state({"configurable": {"thread_id": thread_id}})
    interrupt = _pending(state)
    if interrupt is None:
        raise HTTPException(status_code=409, detail="no pending approval")
    asked = sorted(p["proposal_id"] for p in interrupt["proposals"])
    given = sorted(d.proposal_id for d in body.decisions)
    if given != asked:  # unknown, duplicate or missing ids: validated BEFORE resuming
        raise HTTPException(
            status_code=422,
            detail=f"Give exactly one decision for each pending proposal: {', '.join(asked)}",
        )
    return _stream_run(
        request, t, Command(resume={"decisions": [d.model_dump(mode="json") for d in body.decisions]})
    )


@router.get("/threads/{thread_id}/llm-log")
def llm_log(thread_id: str, request: Request) -> list[PromptRecord]:
    _thread(request, thread_id)
    return _deps(request).promptlog.list(thread_id)


# ---------- tools and studio ----------


@router.get("/tools")
def list_tools(request: Request) -> list[dict]:
    tools = make_tools(_deps(request).store, None, None)  # only names and descriptions are read
    return [{"name": t.name, "description": t.description} for t in tools]


@router.get("/studio")
def studio(request: Request) -> dict:
    # Task 12's studio.py fills features and providers.
    return {"features": [], "providers": [], "usage": _deps(request).promptlog.total_usage().model_dump()}
