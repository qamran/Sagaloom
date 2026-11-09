"""JSON + SSE endpoints (R19.1). Everything here is mounted behind the shared-secret check."""

import asyncio
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from sagaloom.check.badge import with_badges, worst_badge
from sagaloom.export import export_markdown, slugify
from sagaloom.graph.build import run_config
from sagaloom.graph.nodes import RoleModel
from sagaloom.graph.prompts import SYSTEM
from sagaloom.graph.runs import last_run_nodes
from sagaloom.guard import GUARD_POLICY, parse_verdict
from sagaloom.importing.extract import MAX_CHARS
from sagaloom.memory import CAP, count_items, forget, read_preferences
from sagaloom.models import Decision, Entry, MentionRef, PreferenceKey, Usage, World
from sagaloom.studio import build_feature_map, providers_status
from sagaloom.promptlog import PromptLogHandler, PromptRecord
from sagaloom.settings_store import DevSettingsPatch, enabled_tool_names
from sagaloom.store.threads import ThreadKind
from sagaloom.text import message_text
from sagaloom.tools.canon_tools import TOOL_SPECS
from sagaloom.web.imports import import_events
from sagaloom.web.sse import run_turn_events, shielded, sse_response

router = APIRouter()


class NewWorld(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class NewThread(BaseModel):
    world_id: str


class NewMessage(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class DecisionBody(BaseModel):
    decisions: list[Decision]


class NewImport(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_CHARS)
    filename: str | None = Field(default=None, max_length=120, pattern=r"(?i)^[^/\\\x00-\x1f\x7f]+\.(md|txt)$")


def _deps(request: Request):
    return request.app.state.deps


def _thread(request: Request, thread_id: str):
    info = _deps(request).threads.get(thread_id)
    if info is None:
        raise HTTPException(status_code=404, detail="thread not found")
    return info


def message_dict(m: BaseMessage) -> dict:
    """{role, content, name?, tool_calls?, memory?, mode?, import?}; `review` is the author's
    decision note (R18.6), `memory` the `remember` node's note with one result per preference
    (R10.2), `guard` the input guard's notice in place of a blocked message (R13.1), and `import`
    the import endpoint's summary note that opens an import thread (R18.10)."""
    out: dict[str, Any] = {"content": message_text(m.content)}
    if isinstance(m, HumanMessage):
        role = {"review": "review", "memory": "memory", "import": "import"}.get(m.name or "", "user")
        out = {"role": role, **out}
        if m.name:
            out["name"] = m.name
        if role == "memory":
            out["memory"] = list(m.additional_kwargs.get("memory") or [])
        if role == "import":
            out["import"] = m.additional_kwargs.get("import")
        if role == "user" and m.additional_kwargs.get("mode"):
            out["mode"] = m.additional_kwargs["mode"]  # the router's pick for this turn (R6.5)
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
    """The pending interrupt, each check with its badge (derived here, so a checkpoint written
    before badges existed still shows them)."""
    return with_badges(dict(state.interrupts[0].value)) if state.interrupts else None


TITLE_CHARS = 80


def _outcomes(messages: list) -> tuple[int, int]:
    """(approved, rejected), counted from the review notes' `outcome`; a note without one (written
    before outcomes existed), a failed write and a refused commit count as neither."""
    outcomes = [
        m.additional_kwargs.get("outcome")
        for m in messages
        if isinstance(m, HumanMessage) and m.name == "review"
    ]
    return outcomes.count("approved"), outcomes.count("rejected")


def _thread_title(title: str | None, messages: list) -> str | None:
    """The registry title, else the author's first message on one line, cut to TITLE_CHARS."""
    if title:
        return title
    first = next((m for m in messages if isinstance(m, HumanMessage) and not m.name), None)
    if first is None:
        return None
    text = " ".join(message_text(first.content).split())
    return text if len(text) <= TITLE_CHARS else text[: TITLE_CHARS - 1] + "…"


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


def _turn(request: Request, thread) -> tuple[asyncio.Queue, dict, Callable[[], tuple[Usage, Usage]]]:
    """One turn's prompt-event queue, run config (prompt capture under a new turn id) and
    usage function (turn, total), read from the prompt log (R12)."""
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

    return queue, cfg, usage_fn


def _stream_run(request: Request, thread, input_or_command: Any, release: Callable[[], None]):
    d = _deps(request)
    queue, cfg, usage_fn = _turn(request, thread)
    # Shielded: a client that goes away does not cancel the run; the lock is released when the
    # run itself ends (Review Focus 5).
    return sse_response(
        shielded(
            run_turn_events(d.graph, input_or_command, cfg, extra=queue, usage_fn=usage_fn),
            on_finish=release,
            tasks=d.tasks,
        )
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


@router.get("/worlds/{world_id}/entries/{entry_id}/mentions")
def entry_mentions(world_id: str, entry_id: str, request: Request) -> list[MentionRef]:
    """Entries whose body names this one ("Mentioned in", R12.11). Text only: a link alone
    (such as the Mayor's secret membership of the Choir) is not a mention here."""
    d = _deps(request)
    if d.worlds.get(world_id) is None:
        raise HTTPException(status_code=404, detail="world not found")
    entry = d.store.get_entry(world_id, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="entry not found")
    mentions = d.store.find_mentions(world_id, entry, links=False)
    return [
        MentionRef(id=e.id, title=e.title, type=e.type, status=e.status)
        for e in sorted(mentions, key=lambda e: e.id)
    ]


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


# ---------- import (R3.1, R3.2, R18.10) ----------

BLANK_IMPORT = "Paste or upload some text first."
PASTE_TITLE_CHARS = 60


def _first_line(text: str) -> str:
    return next((ln.strip() for ln in text.splitlines() if ln.strip()), "")


@router.post("/worlds/{world_id}/imports")
async def post_import(world_id: str, body: NewImport, request: Request):
    """A new `import` thread: extraction, then the graph run from `check` (spec §3.1)."""
    d = _deps(request)
    if d.worlds.get(world_id) is None:
        raise HTTPException(status_code=404, detail="world not found")
    if not body.text.strip():
        raise HTTPException(status_code=422, detail=BLANK_IMPORT)
    if d.model_for is None:
        raise HTTPException(status_code=503, detail="import is not available")
    label = body.filename or "paste"
    title = body.filename or "Pasted text: " + _first_line(body.text)[:PASTE_TITLE_CHARS]
    thread_id = d.threads.create(world_id, kind="import", title=title)
    try:
        release = await _take_turn(request, thread_id)
    except BaseException:
        d.threads.delete(thread_id)
        raise
    try:
        thread = d.threads.get(thread_id)
        queue, cfg, usage_fn = _turn(request, thread)
        events = import_events(
            d.graph,
            d.store,
            RoleModel(d.model_for, "extractor"),
            world_id,
            thread_id,
            body.text,
            label,
            cfg,
            queue,
            usage_fn,
            d.threads,
        )
        return sse_response(shielded(events, on_finish=release, tasks=d.tasks))
    except BaseException:
        release()
        d.threads.delete(thread_id)
        raise


# ---------- long-term memory (R10.2) ----------

def _memory_world(request: Request, world_id: str):
    d = _deps(request)
    if d.worlds.get(world_id) is None:
        raise HTTPException(status_code=404, detail="world not found")
    if d.memory is None:
        raise HTTPException(status_code=503, detail="memory is not available")
    return d


def _memory_payload(d, settings, world_id: str, prefs: dict) -> dict:
    return {
        "preferences": prefs,
        "count": count_items(prefs),
        "cap": CAP,
        "short_term": {
            "threads": len(d.threads.list(world_id)),
            "checkpoint_file": (Path(settings.data_dir) / "checkpoints.sqlite").as_posix(),
        },
    }


@router.get("/worlds/{world_id}/memory")
async def get_memory(world_id: str, request: Request) -> dict:
    d = _memory_world(request, world_id)
    return _memory_payload(d, request.app.state.settings, world_id, await read_preferences(d.memory, world_id))


@router.delete("/worlds/{world_id}/memory")
async def delete_memory(
    world_id: str, key: PreferenceKey, request: Request, item: str | None = None
) -> dict:
    """Undo or delete: one list item when `item` is given, else the whole key. Idempotent."""
    d = _memory_world(request, world_id)
    return _memory_payload(d, request.app.state.settings, world_id, await forget(d.memory, world_id, key, item))


# ---------- threads ----------


@router.post("/threads")
def create_thread(body: NewThread, request: Request) -> dict:
    d = _deps(request)
    if d.worlds.get(body.world_id) is None:
        raise HTTPException(status_code=404, detail="world not found")
    return {"thread_id": d.threads.create(body.world_id)}


@router.get("/threads")
async def list_threads(
    request: Request,
    pending: bool = False,
    world_id: str | None = None,
    kind: ThreadKind | None = None,
) -> list[dict]:
    """Newest first; `badge` is the worst badge among the pending checks, `running` whether the
    thread's turn lock is held."""
    d = _deps(request)
    out = []
    for t in reversed(d.threads.list(world_id, kind)):
        state = await d.graph.aget_state({"configurable": {"thread_id": t.thread_id}})
        interrupt = _pending(state)
        count = len(interrupt["proposals"]) if interrupt else 0
        if pending and not count:
            continue
        checks = interrupt["checks"].values() if interrupt else []
        messages = (state.values or {}).get("messages") or []
        approved, rejected = _outcomes(messages)
        lock = d.locks.get(t.thread_id)
        out.append(
            {
                "thread_id": t.thread_id,
                "world_id": t.world_id,
                "pending": count,
                "created_at": t.created_at,
                "kind": t.kind,
                "title": _thread_title(t.title, messages),
                "badge": worst_badge(c["badge"] for c in checks),
                "approved": approved,
                "rejected": rejected,
                "running": lock is not None and lock.locked(),
            }
        )
    return out


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str, request: Request) -> dict:
    t = _thread(request, thread_id)
    state = await _deps(request).graph.aget_state({"configurable": {"thread_id": thread_id}})
    values = state.values or {}
    messages = values.get("messages") or []
    interrupt = _pending(state)
    return {
        "thread_id": thread_id,
        "world_id": t.world_id,
        "kind": t.kind,
        "title": _thread_title(t.title, messages),
        "messages": [message_dict(m) for m in messages],
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
            # `entry` persists in the checkpoint, so every run input sets it (R18.10).
            {
                "messages": [HumanMessage(content=body.content)],
                "world_id": t.world_id,
                "entry": "chat",
            },
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


@router.get("/threads/{thread_id}/runs/last")
async def last_run(thread_id: str, request: Request) -> dict:
    _thread(request, thread_id)
    return {"thread_id": thread_id, **await last_run_nodes(_deps(request).graph, thread_id)}


@router.get("/threads/{thread_id}/llm-log")
def llm_log(thread_id: str, request: Request) -> list[PromptRecord]:
    _thread(request, thread_id)
    return _deps(request).promptlog.list(thread_id)


# ---------- tools and studio ----------


@router.get("/tools")
def list_tools(request: Request) -> list[dict]:
    enabled = enabled_tool_names(_deps(request).dev_settings.get())
    return [{**spec, "enabled": spec["name"] in enabled} for spec in TOOL_SPECS]


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
