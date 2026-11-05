"""JSON + SSE endpoints (R19.1). Everything here is mounted behind the shared-secret check."""

import asyncio
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from sagaloom.export import export_markdown, slugify
from sagaloom.graph.build import run_config
from sagaloom.graph.prompts import SYSTEM
from sagaloom.guard import GUARD_POLICY, parse_verdict
from sagaloom.models import Decision, Entry, Usage, World
from sagaloom.studio import build_feature_map, providers_status
from sagaloom.promptlog import PromptLogHandler, PromptRecord
from sagaloom.settings_store import DevSettingsPatch
from sagaloom.text import message_text
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


def message_dict(m: BaseMessage) -> dict:
    """{role, content, name?, tool_calls?}; `review` is the author's decision note (R18.6) and
    `guard` the input guard's notice in place of a blocked message (R13.1)."""
    out: dict[str, Any] = {"content": message_text(m.content)}
    if isinstance(m, HumanMessage):
        out = {"role": "review" if m.name == "review" else "user", **out}
        if m.name:
            out["name"] = m.name
    elif isinstance(m, AIMessage):
        # The input guard's notice for a blocked message (R13.1), like the `review` pattern.
        out = {"role": "guard" if m.name == "guard" else "assistant", **out}
        if m.name == "guard":
            out["name"] = m.name
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


def _turn_config(
    request: Request, thread, emit: Callable[[str, dict], None], turn_id: str
) -> dict:
    d = _deps(request)
    s = d.settings
    secrets = [s.openrouter_api_key.get_secret_value(), s.api_shared_secret.get_secret_value()]
    if s.gemini_api_key:
        secrets.append(s.gemini_api_key.get_secret_value())
    cfg = run_config(thread.thread_id, thread.world_id)
    cfg["callbacks"] = [
        PromptLogHandler(
            d.promptlog, thread.thread_id, emit, settings=s, secrets=secrets, turn_id=turn_id
        )
    ]
    return cfg


async def _take_turn(request: Request, thread_id: str) -> Callable[[], None]:
    """One running turn per thread. Returns an idempotent release; 409 if a turn is running.
    Taken before any state check, so two racing POSTs cannot both pass them."""
    lock = _deps(request).locks.setdefault(thread_id, asyncio.Lock())
    if lock.locked():
        raise HTTPException(status_code=409, detail="turn in progress")
    await lock.acquire()  # uncontended here, so it does not yield between check and acquire
    released = False

    def release() -> None:
        nonlocal released
        if not released:
            released = True
            lock.release()

    return release


def _stream_run(request: Request, thread, input_or_command: Any, release: Callable[[], None]):
    d = _deps(request)
    queue: asyncio.Queue = asyncio.Queue()
    turn_id = uuid.uuid4().hex
    cfg = _turn_config(
        request, thread, lambda name, data: queue.put_nowait({"event": name, "data": data}), turn_id
    )

    def usage_fn() -> tuple[Usage, Usage]:
        return (
            d.promptlog.usage(thread.thread_id, turn_id),
            d.promptlog.usage(thread.thread_id),
        )

    return sse_response(
        run_turn_events(d.graph, input_or_command, cfg, extra=queue, usage_fn=usage_fn),
        on_close=release,
    )


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


@router.get("/worlds/{world_id}/export")
def export_world(
    world_id: str, request: Request, format: str = "md", exclude_secrets: bool = False
) -> Response:
    d = _deps(request)
    world = d.worlds.get(world_id)
    if world is None:
        raise HTTPException(status_code=404, detail="world not found")
    if format != "md":
        raise HTTPException(status_code=422, detail="only format=md is supported")
    data = export_markdown(d.store.list_entries(world_id), exclude_secrets=exclude_secrets)
    filename = f"{slugify(world.name, 'world')}.zip"
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
        "usage": _deps(request).promptlog.usage(thread_id).model_dump(),
    }


@router.post("/threads/{thread_id}/messages")
async def post_message(thread_id: str, body: NewMessage, request: Request):
    t = _thread(request, thread_id)
    release = await _take_turn(request, thread_id)
    try:
        state = await _deps(request).graph.aget_state({"configurable": {"thread_id": thread_id}})
        if state.interrupts:  # a new message would silently drop the pending approval (R15)
            raise HTTPException(status_code=409, detail="approval pending")
        return _stream_run(
            request,
            t,
            {"messages": [HumanMessage(content=body.content)], "world_id": t.world_id},
            release,
        )
    except BaseException:
        release()
        raise


@router.post("/threads/{thread_id}/decisions")
async def post_decisions(thread_id: str, body: DecisionBody, request: Request):
    t = _thread(request, thread_id)
    release = await _take_turn(request, thread_id)
    try:
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
            request,
            t,
            Command(resume={"decisions": [d.model_dump(mode="json") for d in body.decisions]}),
            release,
        )
    except BaseException:
        release()
        raise


@router.get("/threads/{thread_id}/llm-log")
def llm_log(thread_id: str, request: Request) -> list[PromptRecord]:
    _thread(request, thread_id)
    return _deps(request).promptlog.list(thread_id)


# ---------- tools and studio ----------


@router.get("/tools")
def list_tools(request: Request) -> list[dict]:
    tools = make_tools(_deps(request).store, None, None)  # only names and descriptions are read
    return [{"name": t.name, "description": t.description} for t in tools]


class ModelChoice(BaseModel):
    role: str
    model: str


def _models_payload(request: Request) -> dict:
    d = _deps(request)
    return {
        "mapping": d.model_settings.get_model_settings(),
        "allowed": [m.model_dump() for m in d.settings.allowed_models],
    }


@router.get("/settings/models")
def get_models(request: Request) -> dict:
    return _models_payload(request)


@router.put("/settings/models")
def put_models(body: ModelChoice, request: Request) -> dict:
    try:
        _deps(request).model_settings.set_model(body.role, body.model)  # type: ignore[arg-type]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _models_payload(request)


def _dev_payload(request: Request) -> dict:
    return {
        "settings": _deps(request).dev_settings.get().model_dump(),
        "defaults": {"agent_system_prompt": SYSTEM},
        "guard_policy": GUARD_POLICY,
    }


@router.get("/settings")
def get_dev_settings(request: Request) -> dict:
    return _dev_payload(request)


@router.put("/settings")
def put_dev_settings(body: DevSettingsPatch, request: Request) -> dict:
    _deps(request).dev_settings.update(body)
    return _dev_payload(request)


@router.get("/guard/log")
def guard_log(request: Request, limit: int = 20) -> list[dict]:
    """Recent input-guard verdicts, read from the prompt log (role `guard`)."""
    rows = []
    for rec in _deps(request).promptlog.list_by_role("guard", max(1, min(limit, 100))):
        v = parse_verdict(rec.response)
        rows.append(
            {
                "thread_id": rec.thread_id,
                "started_at": rec.started_at,
                "model": rec.model,
                "verdict": v.verdict if v else "unknown",
                "reason": v.reason if v else "",
            }
        )
    return rows


def _mermaid(graph: Any) -> str:
    try:
        return graph.get_graph().draw_mermaid()
    except Exception:
        return ""


@router.get("/studio")
def studio(request: Request) -> dict:
    d = _deps(request)
    log = d.promptlog
    return {
        "features": [c.model_dump() for c in build_feature_map(d.settings, d)],
        "providers": [p.model_dump() for p in providers_status(d.settings, d.model_settings.get_model_settings())],
        "usage": {**log.total_usage().model_dump(), "by_model": log.usage_by_model()},
        "mermaid": _mermaid(d.graph),
    }
