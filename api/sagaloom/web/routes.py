"""JSON + SSE endpoints (R19.1). Everything here is mounted behind the shared-secret check."""

import asyncio
import uuid
from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict, Field

from sagaloom import budget
from sagaloom.budget import OverBudget, budget_reset_date, over_budget
from sagaloom.config import load_model_ratings
from sagaloom.export import export_markdown, slugify
from sagaloom.graph.build import CHECKPOINT_FILE, run_config
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
from sagaloom.text import first_line, message_text
from sagaloom.tools.specs import TOOL_SPECS
from sagaloom.web.access import require_admin, thread_for, user_of, world_for
from sagaloom.web.imports import import_events, wiki_import_events
from sagaloom.web.sse import run_turn_events, shielded, sse_response
from sagaloom.web.thread_list import (
    list_rows,
    pending_interrupt,
    refresh_summary,
    thread_title,
    with_summary,
)
from sagaloom.wiki.pages import BadWikiUrl, parse_page_urls

router = APIRouter()


def check_budget(deps: Any, user: Any) -> None:
    """The budget check as HTTP: 402 with the budget message when the account is over it."""
    try:
        budget.check_budget(deps, user)
    except OverBudget as e:
        raise HTTPException(status_code=402, detail=str(e)) from e


class NewWorld(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class NewThread(BaseModel):
    world_id: str


class NewMessage(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class DecisionBody(BaseModel):
    decisions: list[Decision]


class TextImport(BaseModel):
    kind: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=MAX_CHARS)
    # The name part refuses path separators and every control, line and paragraph separator
    # (Cc, Zl, Zp: the classes `memory._one_line` refuses), so the label stays one line.
    filename: str | None = Field(
        default=None, max_length=120, pattern=r"(?i)^[^/\\\p{Cc}\p{Zl}\p{Zp}]+\.(md|txt)$"
    )


class WikiImport(BaseModel):
    kind: Literal["wiki"]
    # 1 to 10 page URLs: `parse_page_urls` checks the count, so a wrong count gets its copy
    # (R-W3-8) rather than a schema error; the request body cap bounds the list.
    urls: list[Annotated[str, Field(max_length=2000)]]


NewImport = WikiImport | TextImport


def _deps(request: Request):
    return request.app.state.deps


def message_dict(m: BaseMessage) -> dict:
    """{role, content, name?, tool_calls?, memory?, mode?, import?, turn_id?}; `review` is the
    author's decision note (R18.6), `memory` the `remember` node's note with one result per
    preference (R10.2), `guard` the input guard's notice in place of a blocked message (R13.1),
    and `import` the import endpoint's summary note that opens an import thread (R18.10).
    `turn_id` is the id of the turn that wrote the message (its PromptLog `run_id`, M4 §3.3);
    messages from before M4, and tool and import messages, have none."""
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
    if m.additional_kwargs.get("turn_id"):
        out["turn_id"] = m.additional_kwargs["turn_id"]
    return out


def _turn_config(
    request: Request, thread, emit: Callable[[str, dict], None], turn_id: str
) -> dict:
    d = _deps(request)
    s = d.settings
    secrets = [s.openrouter_api_key.get_secret_value(), s.api_shared_secret.get_secret_value()]
    if s.gemini_api_key:
        secrets.append(s.gemini_api_key.get_secret_value())
    cfg = run_config(thread.thread_id, thread.world_id)
    cfg["configurable"]["turn_id"] = turn_id  # the nodes stamp it on what they append (M4 §3.3)
    # The calls are the cost of the world's owner, not of whoever asked (the same today: only
    # owners reach a thread), so it stays right when sharing comes (M5 spec §5.2).
    world = d.worlds.get(thread.world_id)
    cfg["callbacks"] = [
        PromptLogHandler(
            d.promptlog,
            thread.thread_id,
            emit,
            settings=s,
            secrets=secrets,
            turn_id=turn_id,
            user_id=world.owner_id if world is not None else None,
            clock=d.now,  # the clock `month_spend` and the budget check read
        )
    ]
    return cfg


async def _take_turn(request: Request, thread_id: str) -> Callable[[], None]:
    """One running turn per thread. Returns an idempotent release; 409 if a turn is running.
    Taken before any state check, so two racing POSTs cannot both pass them."""
    locks = _deps(request).locks
    lock = locks.setdefault(thread_id, asyncio.Lock())
    if lock.locked():
        raise HTTPException(status_code=409, detail="turn in progress")
    await lock.acquire()  # uncontended here, so it does not yield between check and acquire
    released = False

    def release() -> None:
        nonlocal released
        if not released:
            released = True
            lock.release()
            # Prune, so `locks` does not grow with every thread ever used. Nobody waits on a
            # turn lock (a second request 409s), and a missing lock reads as "not running".
            if locks.get(thread_id) is lock:
                del locks[thread_id]

    try:
        # The list summary is from before this turn: clear it, so a turn cut off mid-way leaves
        # none to go stale (it is written again before the turn's `done` or `error`).
        _deps(request).threads.set_summary(thread_id, None)
    except BaseException:
        release()
        raise
    return release


def _turn(
    request: Request, thread, turn_id: str | None = None
) -> tuple[asyncio.Queue, dict, Callable[[], tuple[Usage, Usage]]]:
    """One turn's prompt-event queue, run config (prompt capture under `turn_id`, else a new
    one) and usage function (turn, total), read from the prompt log (R12)."""
    d = _deps(request)
    queue: asyncio.Queue = asyncio.Queue()
    turn_id = turn_id or uuid.uuid4().hex
    cfg = _turn_config(
        request, thread, lambda name, data: queue.put_nowait({"event": name, "data": data}), turn_id
    )

    def usage_fn() -> tuple[Usage, Usage]:
        return (
            d.promptlog.usage(thread.thread_id, turn_id),
            d.promptlog.usage(thread.thread_id),
        )

    return queue, cfg, usage_fn


def _stream_run(
    request: Request,
    thread,
    input_or_command: Any,
    release: Callable[[], None],
    turn_id: str | None = None,
    no_agent: bool = False,
):
    """Streams one graph run. `no_agent` ends a chat run after `commit` (the graph's
    `route_after_commit`), so no model is called: rejections resumed over budget."""
    d = _deps(request)
    queue, cfg, usage_fn = _turn(request, thread, turn_id)
    if no_agent:
        cfg["configurable"]["no_agent"] = True
    # Shielded: a client that goes away does not cancel the run; the lock is released when the
    # run itself ends (Review Focus 5).
    return sse_response(
        shielded(
            with_summary(
                run_turn_events(d.graph, input_or_command, cfg, extra=queue, usage_fn=usage_fn),
                lambda: refresh_summary(d, thread.thread_id),
            ),
            on_finish=release,
            tasks=d.tasks,
        )
    )


# ---------- worlds and entries ----------


@router.get("/worlds")
def list_worlds(request: Request) -> list[World]:
    return _deps(request).worlds.owned_by(user_of(request).id)


@router.post("/worlds")
def create_world(body: NewWorld, request: Request) -> World:
    d = _deps(request)
    # An id the canon store still holds records under is skipped (a lost worlds.json).
    return d.worlds.create(body.name.strip() or "World", owner_id=user_of(request).id, in_use=d.store.has_world)


@router.get("/worlds/{world_id}/entries")
def list_entries(world_id: str, request: Request) -> list[Entry]:
    world_for(request, world_id)
    return _deps(request).store.list_entries(world_id)


@router.get("/worlds/{world_id}/entries/{entry_id}")
def get_entry(world_id: str, entry_id: str, request: Request) -> Entry:
    world_for(request, world_id)
    entry = _deps(request).store.get_entry(world_id, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="entry not found")
    return entry


@router.get("/worlds/{world_id}/entries/{entry_id}/mentions")
def entry_mentions(world_id: str, entry_id: str, request: Request) -> list[MentionRef]:
    """Entries whose body names this one ("Mentioned in", R12.11). Text only: a link alone
    (such as the Mayor's secret membership of the Choir) is not a mention here."""
    world_for(request, world_id)
    d = _deps(request)
    entry = d.store.get_entry(world_id, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="entry not found")
    mentions = d.store.find_mentions(world_id, entry)
    return [
        MentionRef(id=e.id, title=e.title, type=e.type, status=e.status)
        for e in sorted(mentions, key=lambda e: e.id)
    ]


@router.get("/worlds/{world_id}/export")
def export_world(
    world_id: str, request: Request, format: str = "md", exclude_secrets: bool = False
) -> Response:
    world = world_for(request, world_id)
    d = _deps(request)
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


@router.post("/worlds/{world_id}/imports")
async def post_import(world_id: str, body: NewImport, request: Request):
    """A new `import` thread: extraction, then the graph run from `check` (spec §3.1). A wiki
    import fetches its pages first (M3 design §5)."""
    world_for(request, world_id)
    d = _deps(request)
    check_budget(d, user_of(request))  # before any import kind starts (spec §5.5a)
    if isinstance(body, WikiImport):
        return await _post_wiki_import(world_id, body, request)
    if not body.text.strip():
        raise HTTPException(status_code=422, detail=BLANK_IMPORT)
    if d.model_for is None:
        raise HTTPException(status_code=503, detail="import is not available")
    label = body.filename or "paste"
    title = body.filename or "Pasted text: " + first_line(body.text)[:PASTE_TITLE_CHARS]
    return await _stream_import(
        request,
        world_id,
        title,
        lambda thread_id, cfg, queue, usage_fn: import_events(
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
        ),
    )


async def _post_wiki_import(world_id: str, body: WikiImport, request: Request):
    d = _deps(request)
    try:
        pages = parse_page_urls(body.urls)
    except BadWikiUrl as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    if d.wiki is None or d.model_for is None:
        raise HTTPException(status_code=503, detail="import is not available")
    return await _stream_import(
        request,
        world_id,
        f"Fan wiki: {pages[0].host} ({len(pages)} pages)",
        lambda thread_id, cfg, queue, usage_fn: wiki_import_events(
            d.graph,
            d.store,
            d.wiki,
            RoleModel(d.model_for, "extractor"),
            world_id,
            thread_id,
            pages,
            cfg,
            queue,
            usage_fn,
            d.threads,
        ),
    )


async def _stream_import(request: Request, world_id: str, title: str, make_events: Callable[..., Any]):
    """A new `import` thread under its turn lock, streaming `make_events(thread_id, cfg, queue,
    usage_fn)` shielded; the row goes again when the stream can't start."""
    d = _deps(request)
    thread_id = d.threads.create(world_id, kind="import", title=title)
    try:
        release = await _take_turn(request, thread_id)
    except BaseException:
        d.threads.delete(thread_id)
        raise
    try:
        thread = d.threads.get(thread_id)
        queue, cfg, usage_fn = _turn(request, thread)
        events = make_events(thread_id, cfg, queue, usage_fn)
        events = with_summary(events, lambda: refresh_summary(d, thread_id))
        return sse_response(shielded(events, on_finish=release, tasks=d.tasks))
    except BaseException:
        release()
        d.threads.delete(thread_id)
        raise


# ---------- long-term memory (R10.2) ----------

def _memory_world(request: Request, world_id: str):
    world_for(request, world_id)
    d = _deps(request)
    if d.memory is None:
        raise HTTPException(status_code=503, detail="memory is not available")
    return d


def _memory_payload(d, world_id: str, prefs: dict) -> dict:
    return {
        "preferences": prefs,
        "count": count_items(prefs),
        "cap": CAP,
        "short_term": {
            "threads": len(d.threads.list(world_id)),
            "checkpoint_file": CHECKPOINT_FILE,  # the name only: a path is the server's business
        },
    }


@router.get("/worlds/{world_id}/memory")
async def get_memory(world_id: str, request: Request) -> dict:
    d = _memory_world(request, world_id)
    return _memory_payload(d, world_id, await read_preferences(d.memory, world_id))


@router.delete("/worlds/{world_id}/memory")
async def delete_memory(
    world_id: str, key: PreferenceKey, request: Request, item: str | None = None
) -> dict:
    """Undo or delete: one list item when `item` is given, else the whole key. Idempotent."""
    d = _memory_world(request, world_id)
    async with d.memory_locks.hold(world_id):
        prefs = await forget(d.memory, world_id, key, item)
    return _memory_payload(d, world_id, prefs)


# ---------- threads ----------


@router.post("/threads")
def create_thread(body: NewThread, request: Request) -> dict:
    world_for(request, body.world_id)
    d = _deps(request)
    return {"thread_id": d.threads.create(body.world_id)}


@router.get("/threads")
async def list_threads(
    request: Request,
    pending: bool = False,
    world_id: str | None = None,
    kind: ThreadKind | None = None,
) -> list[dict]:
    """The user's threads, newest first; `badge` is the worst badge among the pending checks,
    `running` whether the thread's turn lock is held. `world_id` is a list filter, not an id
    route: a world that is not the user's lists nothing (`[]`), it does not 404."""
    d = _deps(request)
    world_ids = {w.id for w in d.worlds.owned_by(user_of(request).id)}
    # Read from the registry's summaries, not every checkpoint (`web/thread_list.py`).
    return await list_rows(d, world_ids=world_ids, pending=pending, world_id=world_id, kind=kind)


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str, request: Request) -> dict:
    t = thread_for(request, thread_id)
    state = await _deps(request).graph.aget_state({"configurable": {"thread_id": thread_id}})
    values = state.values or {}
    messages = values.get("messages") or []
    interrupt = pending_interrupt(state)
    return {
        "thread_id": thread_id,
        "world_id": t.world_id,
        "kind": t.kind,
        "title": thread_title(t.title, messages),
        "messages": [message_dict(m) for m in messages],
        "pending_interrupt": (
            {"proposals": interrupt["proposals"], "checks": interrupt["checks"],
             **({"error": interrupt["error"]} if interrupt.get("error") else {})}
            if interrupt
            else None
        ),
        "usage": _deps(request).promptlog.usage(thread_id).model_dump(),
        "turns": [t.model_dump() for t in _deps(request).promptlog.usage_by_turn(thread_id)],
    }


@router.post("/threads/{thread_id}/messages")
async def post_message(thread_id: str, body: NewMessage, request: Request):
    t = thread_for(request, thread_id)
    check_budget(_deps(request), user_of(request))  # before the lock: a refusal changes nothing
    release = await _take_turn(request, thread_id)
    try:
        state = await _deps(request).graph.aget_state({"configurable": {"thread_id": thread_id}})
        if state.interrupts:  # a new message would silently drop the pending approval (R15)
            raise HTTPException(status_code=409, detail="approval pending")
        # The author's message is built here, before the run, so the turn id is made here too.
        turn_id = uuid.uuid4().hex
        return _stream_run(
            request,
            t,
            # `entry` persists in the checkpoint, so every run input sets it (R18.10).
            {
                "messages": [
                    HumanMessage(content=body.content, additional_kwargs={"turn_id": turn_id})
                ],
                "world_id": t.world_id,
                "entry": "chat",
            },
            release,
            turn_id=turn_id,
        )
    except BaseException:
        release()
        raise


@router.post("/threads/{thread_id}/decisions")
async def post_decisions(thread_id: str, body: DecisionBody, request: Request):
    t = thread_for(request, thread_id)
    # Decisions that only reject stay available over budget (spec §5.5a), but then the run ends
    # after the commit: the agent's reply would be unpaid spend. Any other decision is checked
    # before the lock, so a refusal changes nothing.
    reject_only = all(d.action == "reject" for d in body.decisions)
    no_agent = reject_only and over_budget(_deps(request), user_of(request))
    if not reject_only:
        check_budget(_deps(request), user_of(request))
    release = await _take_turn(request, thread_id)
    try:
        state = await _deps(request).graph.aget_state({"configurable": {"thread_id": thread_id}})
        interrupt = pending_interrupt(state)
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
            no_agent=no_agent,
        )
    except BaseException:
        release()
        raise


@router.get("/threads/{thread_id}/runs/last")
async def last_run(thread_id: str, request: Request) -> dict:
    thread_for(request, thread_id)
    return {"thread_id": thread_id, **await last_run_nodes(_deps(request).graph, thread_id)}


@router.get("/threads/{thread_id}/llm-log")
def llm_log(thread_id: str, request: Request) -> list[PromptRecord]:
    thread_for(request, thread_id)
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
    """The role mapping and the allowlist; each model carries its public benchmark rating (None
    when the leaderboard has no score for it), and `ratings_source` says where they come from."""
    d = _deps(request)
    ratings = load_model_ratings()
    scores = ratings.get("ratings", {})
    return {
        "mapping": d.model_settings.get_model_settings(),
        "allowed": [{**m.model_dump(), "rating": scores.get(m.id)} for m in d.settings.allowed_models],
        "ratings_source": {k: ratings.get(k) for k in ("source", "url", "retrieved", "note")},
    }


@router.get("/settings/models")
def get_models(request: Request) -> dict:
    return _models_payload(request)


@router.put("/settings/models", dependencies=[Depends(require_admin)])
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


@router.put("/settings", dependencies=[Depends(require_admin)])
def put_dev_settings(body: DevSettingsPatch, request: Request) -> dict:
    _deps(request).dev_settings.update(body)
    return _dev_payload(request)


Scope = Literal["mine", "all"]


def _scope_user(request: Request, scope: Scope) -> str | None:
    """Whose prompt records a Studio panel reads: the caller's (`mine`), or everyone's (`all`,
    the admin's "All users" switch; 403 for anyone else). M5 spec §5.2."""
    if scope == "all":
        require_admin(request)
        return None
    return user_of(request).id


def _world_threads(request: Request, scope: Scope, world_id: str | None) -> list[str] | None:
    """The thread ids of the world selected in the header (404 when it is not the caller's), so
    a Studio panel shows only that world; None for every world: no `world_id`, or the admin's
    app-wide `scope=all`."""
    if world_id is None or scope == "all":
        return None
    world_for(request, world_id)
    return [t.thread_id for t in _deps(request).threads.list(world_id)]


@router.get("/guard/log")
def guard_log(
    request: Request, limit: int = 20, scope: Scope = "mine", world_id: str | None = None
) -> list[dict]:
    """Recent input-guard verdicts, read from the prompt log (role `guard`): the caller's own,
    or everyone's for the admin with `scope=all`; only one world's with `world_id`."""
    rows = []
    user_id = _scope_user(request, scope)
    thread_ids = _world_threads(request, scope, world_id)
    for rec in _deps(request).promptlog.list_by_role("guard", max(1, min(limit, 100)), user_id, thread_ids):
        if rec.response is None or rec.response.get("error"):  # the call raised: the message was blocked
            verdict, reason = "error", (rec.response or {}).get("error", "")
        else:  # a response that does not parse is "unknown"
            v = parse_verdict(rec.response)
            verdict, reason = (v.verdict, v.reason) if v else ("unknown", "")
        rows.append(
            {
                "thread_id": rec.thread_id,
                "started_at": rec.started_at,
                "model": rec.model,
                "verdict": verdict,
                "reason": reason,
            }
        )
    return rows


def _mermaid(graph: Any) -> str:
    try:
        return graph.get_graph().draw_mermaid()
    except Exception:
        return ""


@router.get("/studio")
def studio(request: Request, scope: Scope = "mine", world_id: str | None = None) -> dict:
    """Usage and the Feature map's cost line are the caller's own, and only `world_id`'s when it
    is given; the admin may ask for `scope=all` (every user's calls, ownerless ones too, in every
    world)."""
    d = _deps(request)
    log = d.promptlog
    user_id = _scope_user(request, scope)
    thread_ids = _world_threads(request, scope, world_id)
    world = world_id if thread_ids is not None else None
    return {
        "features": [c.model_dump() for c in build_feature_map(d.settings, d, user_id, world)],
        "providers": [p.model_dump() for p in providers_status(d.settings, d.model_settings.get_model_settings())],
        "usage": {
            **log.total_usage(user_id, thread_ids).model_dump(),
            "by_model": log.usage_by_model(user_id, thread_ids),
        },
        "mermaid": _mermaid(d.graph),
    }


# ---------- the signed-in account (M5 spec §5.4, §5.5a) ----------


class Me(BaseModel):
    id: str
    email: str
    display_name: str
    is_admin: bool
    last_world_id: str | None
    month_spend_usd: float  # this calendar month (UTC), from the prompt log
    monthly_budget_usd: float | None  # None: no limit (the admin)
    budget_resets_on: str  # the first day of next month (UTC), YYYY-MM-DD
    over_budget: bool  # spend >= budget, the 402 rule (never the admin)


class MePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_world_id: str | None


def _me(request: Request, last_world_id: str | None) -> Me:
    d = _deps(request)
    user = user_of(request)
    now = d.now()
    return Me(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        last_world_id=last_world_id,
        month_spend_usd=d.promptlog.month_spend(user.id, now),
        monthly_budget_usd=None if user.is_admin else d.dev_settings.get().monthly_budget_usd,
        budget_resets_on=budget_reset_date(now).isoformat(),
        over_budget=over_budget(d, user, now),
    )


@router.get("/me")
def get_me(request: Request) -> Me:
    return _me(request, user_of(request).last_world_id)


@router.put("/me")
def put_me(body: MePatch, request: Request) -> Me:
    """Remembers the world picker's choice; 404 for a world that is not the user's."""
    if body.last_world_id is not None:
        world_for(request, body.last_world_id)
    _deps(request).users.set_last_world(user_of(request).id, body.last_world_id)
    return _me(request, body.last_world_id)
