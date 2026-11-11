"""Graph nodes (R18). Only `commit` writes to the store, and it refuses anything that has
not been checked and approved (R18.3)."""

import logging
import threading
from collections.abc import Callable
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.graph import END
from langgraph.prebuilt import ToolNode
from langgraph.store.base import BaseStore
from langgraph.types import Command, interrupt
from pydantic import ValidationError

import sagaloom.router as router_mod
from sagaloom.check.contradiction import CHECK_FAILED_EXPLANATION, check_proposal
from sagaloom.check.myth import apply_save_as_myth
from sagaloom.graph.prompts import SYSTEM
from sagaloom.graph.state import Role, SagaState
from sagaloom.guard import BLOCK_COPY, classify
from sagaloom.locks import KeyedLocks
from sagaloom.memory import (
    agent_note,
    apply_updates,
    read_preferences,
    render_preferences,
    unavailable,
)
from sagaloom.models import (
    PROVENANCE_FIELDS,
    CheckResult,
    Decision,
    Entry,
    Flag,
    Proposal,
)
from sagaloom.provenance import merge_provenance
from sagaloom.settings_store import DevSettings, enabled_tool_names
from sagaloom.store.canon import DuplicateTitleError, VersionConflictError
from sagaloom.structured import ChatModelLike  # noqa: F401  (re-exported; defined in structured)
from sagaloom.text import message_text

log = logging.getLogger(__name__)

ModelFor = Callable[[Role], BaseChatModel]


class RoleModel:
    """Resolves `model_for(role)` on every use, so a per-role model switch takes effect on
    the next call even though the tools are built once. It forwards attributes instead of
    subclassing BaseChatModel, which is why the parameters it fills are typed `ChatModelLike`."""

    def __init__(self, model_for: ModelFor, role: Role):
        self._model_for = model_for
        self._role = role

    def __getattr__(self, name: str) -> Any:
        return getattr(self._model_for(self._role), name)


ReviewOutcome = Literal["approved", "rejected", "failed", "refused"]


def _review(text: str, pid: str, outcome: ReviewOutcome) -> HumanMessage:
    """The author's decision note (R18.6). `outcome` is what `GET /threads` counts: `failed` is
    approved but the write failed, `refused` is not checked and approved or proposed in another
    world (nothing written)."""
    return HumanMessage(
        name="review", content=text, additional_kwargs={"proposal_id": pid, "outcome": outcome}
    )


def with_turn(msgs: list[BaseMessage], config: RunnableConfig | None) -> list[BaseMessage]:
    """Copies of `msgs` stamped with the run's turn id (`configurable.turn_id`, set by the web
    routes), so the chat can attach the turn's cost to them (M4 §3.3). Kept in
    `additional_kwargs`, as the router's `mode`; no model request carries it. Unchanged when the
    run has no turn id (a test or script run)."""
    turn_id = ((config or {}).get("configurable") or {}).get("turn_id")
    if not turn_id:
        return msgs
    return [
        m.model_copy(update={"additional_kwargs": {**m.additional_kwargs, "turn_id": turn_id}})
        for m in msgs
    ]


# ---------- routing ----------


def route_entry(state: SagaState) -> Literal["guard", "check"]:
    """START: an import run goes straight to `check` (its proposals come from the import
    endpoint, not a tool call); anything else, including a missing `entry`, is a chat turn."""
    return "check" if state.get("entry") == "import" else "guard"


def route_after_commit(state: SagaState) -> Literal["agent", "check", "__end__"]:
    """A chat turn tells the agent (it reads the refused note itself). An import thread has no
    agent: it ends once nothing is pending, but a proposal `commit` refused stays pending and
    would be stranded, so it goes back through `check` and the gate asks again.

    Cost: `check` skips a proposal that already has a check result, and `commit` keeps the check
    of a refused one, so the re-check makes no new judge call; the gate interrupts again with the
    kept check. A proposal refused for a world mismatch is refused again on every cycle, so each
    cycle needs a human decision; it never loops on its own."""
    if state.get("entry") != "import":
        return "agent"
    return "check" if state.get("pending_proposals") else END


def route_after_agent(state: SagaState) -> Literal["tools", "__end__"]:
    msgs = state.get("messages") or []
    last = msgs[-1] if msgs else None
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


def route_after_tools(state: SagaState) -> Literal["remember", "check", "agent"]:
    """Queued preferences go to `remember` first (spec §3.5: after `check` they would be lost
    when the turn pauses at the gate, which resumes through `commit -> agent`). Otherwise as
    `route_after_remember`."""
    if state.get("memory_updates"):  # older checkpoints have no such key
        return "remember"
    return route_after_remember(state)


def route_after_remember(state: SagaState) -> Literal["check", "agent"]:
    """Any proposal not yet checked AND decided goes to `check` (and from there the gate)."""
    checks = state.get("check_results") or {}
    decisions = state.get("decisions") or {}
    for p in state.get("pending_proposals") or []:
        if p.proposal_id not in checks or p.proposal_id not in decisions:
            return "check"
    return "agent"


def route_after_guard(state: SagaState) -> Literal["router", "__end__"]:
    return "router" if state.get("guard_verdict") in ("safe", "off") else END


# ---------- input guard ----------


def _unchecked_run(msgs: list) -> list[HumanMessage]:
    """The author's messages since the last non-author message. Normally just the new one, but a
    turn cancelled during the guard leaves its message in history unclassified, so it is checked
    (and removed if blocked) together with the next one."""
    run: list[HumanMessage] = []
    for m in reversed(msgs):
        if not isinstance(m, HumanMessage) or m.name:
            break
        run.append(m)
    return run[::-1]


def make_guard_node(model_for: ModelFor, dev: Callable[[], DevSettings] = DevSettings):
    """Classifies the author's new message before the agent sees it (R13.1). Fails closed: any
    error blocks the message. A blocked message is removed from the history, so an injection
    never sits in what the agent reads on later turns, and replaced by the guard's notice."""

    async def guard(state: SagaState, config: RunnableConfig | None = None) -> dict:
        run = _unchecked_run(state.get("messages") or [])
        if not run:
            return {"guard_verdict": "safe"}  # only the author's own messages are classified
        if not dev().guard_enabled:
            return {"guard_verdict": "off"}
        text = "\n\n".join(message_text(m.content) for m in run)  # one call for the whole run
        try:
            verdict = (await classify(model_for("guard"), text)).verdict
        except Exception as exc:
            log.warning("guard failed, blocking the message: %s", type(exc).__name__)
            verdict = "error"
        if verdict == "safe":
            return {"guard_verdict": "safe"}
        return {
            "guard_verdict": verdict,
            "messages": [
                *(RemoveMessage(id=m.id) for m in run),
                *with_turn([AIMessage(name="guard", content=BLOCK_COPY[verdict])], config),
            ],
        }

    return guard


# ---------- router ----------


def make_router_node(model_for: ModelFor):
    """Picks this turn's mode (R6.5). Never blocks the turn: on any error the mode is None and
    the agent runs with no mode section. The mode is also stamped on the author's message (same
    id, so `add_messages` replaces it in place) for the chat's mode chip after a reload."""

    async def router(state: SagaState) -> dict:
        run = _unchecked_run(state.get("messages") or [])
        if not run:
            return {}
        text = "\n\n".join(message_text(m.content) for m in run)  # one call, as in the guard
        try:
            mode = (await router_mod.route(model_for("router"), text)).mode
        except Exception as exc:
            log.warning("router failed, running the turn without a mode: %s", type(exc).__name__)
            return {"mode": None}
        last = run[-1]
        stamped = last.model_copy(update={"additional_kwargs": {**last.additional_kwargs, "mode": mode}})
        return {"mode": mode, "messages": [stamped]}

    return router


# ---------- agent ----------


def make_agent_node(
    model_for: ModelFor,
    tools: list[BaseTool],
    dev: Callable[[], DevSettings] = DevSettings,
    memory_store: BaseStore | None = None,
):
    async def agent(state: SagaState, config: RunnableConfig) -> dict:
        d = dev()  # read every turn, so a settings change applies from the next one
        params: dict[str, Any] = {"temperature": d.agent_temperature}
        if d.agent_max_tokens:
            params["max_tokens"] = d.agent_max_tokens
        enabled = enabled_tool_names(d)
        bound = [t for t in tools if t.name in enabled]
        llm = model_for("agent").bind_tools(bound).bind(**params)
        base = d.agent_system_prompt or SYSTEM
        # Read on every call, so a preference stored in any thread of this world applies from
        # the next call. Author-stated (gated by `remember`), so it may sit in the system prompt.
        world_id = state.get("world_id")
        prefs = await read_preferences(memory_store, world_id) if memory_store and world_id else {}
        block = render_preferences(prefs)
        # The mode section sits between the base prompt and the preferences. Advisory (spec F3):
        # the mode is still set and shown, but no section is appended.
        mode = state.get("mode")
        section = "" if not mode or router_mod.ROUTER_ADVISORY else "\n\n" + router_mod.MODE_SECTIONS[mode]
        system = SystemMessage(content=base + section + ("\n\n" + block if block else ""))
        reply = await llm.ainvoke([system, *state.get("messages", [])], config)
        return {"messages": with_turn([reply], config)}

    return agent


def _off_copy(name: str) -> str:
    return f"Tool '{name}' is turned off in Studio."


def _tool_messages(update: Any) -> list[ToolMessage]:
    """The ToolMessages inside one piece of a ToolNode result (a dict, a list, or a Command)."""
    if isinstance(update, Command):
        update = update.update
    if isinstance(update, dict):
        update = update.get("messages")
    if isinstance(update, ToolMessage):
        return [update]
    return [m for m in update or [] if isinstance(m, ToolMessage)] if isinstance(update, list) else []


def make_tools_node(tools: list[BaseTool], dev: Callable[[], DevSettings] = DevSettings):
    """`ToolNode` that refuses a tool turned off in Studio (R11.G3). The agent only binds enabled
    tools, but a disabled one can still be named from history or by a stale turn: it gets an
    error ToolMessage with the same call id and never runs. The enabled calls of the same AI
    message go to the real ToolNode, and the results come back in the original call order."""
    inner = ToolNode(tools, handle_tool_errors=True)

    async def tools_node(state: SagaState, config: RunnableConfig):
        # Only a real tool that is switched off is refused; an invented name goes to ToolNode,
        # which answers with its own invalid-name error.
        disabled = {t.name for t in tools} - enabled_tool_names(dev())  # read every turn
        msgs = list(state.get("messages") or [])
        last = msgs[-1] if msgs else None
        calls = list(getattr(last, "tool_calls", None) or [])
        if not any(c["name"] in disabled for c in calls):
            return await inner.ainvoke(state, config)
        kept = [c for c in calls if c["name"] not in disabled]
        merged: dict[str, list] = {}  # call id -> the ToolNode updates that answer it
        leftovers: list = []
        if kept:
            narrowed = last.model_copy(update={"tool_calls": kept})
            result = await inner.ainvoke({**state, "messages": [*msgs[:-1], narrowed]}, config)
            # A dict when no tool returned a Command, else a list mixing dicts and Commands.
            for part in result if isinstance(result, list) else [result]:
                found = _tool_messages(part)
                if isinstance(part, dict):  # one dict holds all the plain ToolMessages
                    for m in found:
                        merged.setdefault(m.tool_call_id, []).append(m)
                elif found:
                    merged.setdefault(found[0].tool_call_id, []).append(part)
                else:
                    leftovers.append(part)
        ordered: list = []
        for c in calls:
            if c["name"] not in disabled:
                ordered.extend(merged.pop(c["id"], []))
            else:
                ordered.append(
                    ToolMessage(
                        content=_off_copy(c["name"]),
                        tool_call_id=c["id"],
                        name=c["name"],
                        status="error",
                    )
                )
        for rest in merged.values():
            ordered.extend(rest)
        ordered.extend(leftovers)
        if not any(isinstance(u, Command) for u in ordered):
            return {"messages": ordered}
        return [u if isinstance(u, Command) else {"messages": [u]} for u in ordered]

    return tools_node


# ---------- remember ----------


def _author_text(msgs: list) -> str:
    """The latest message the author typed: an unnamed HumanMessage (review and memory notes are
    named). Retrieved text arrives in ToolMessages, so it can never be this message."""
    for m in reversed(msgs):
        if isinstance(m, HumanMessage) and not m.name:
            return message_text(m.content)
    return ""


def make_remember_node(memory_store: BaseStore, locks: KeyedLocks):
    """The only writer of preferences (R18.2). No approval gate: preferences are not canon, and
    every write is shown in chat and undoable. The verbatim gate in `apply_updates` is the
    injection defence (R10.2). `locks` is the app's per-world memory lock, shared with the
    memory routes: two threads of the same world, or a remember and an Undo, must not
    interleave their read-modify-write (a lost update, or a way past the cap)."""

    async def remember(state: SagaState, config: RunnableConfig | None = None) -> dict:
        world_id = state["world_id"]
        updates = list(state.get("memory_updates") or [])
        author = _author_text(state.get("messages") or [])
        try:
            async with locks.hold(world_id):
                results = await apply_updates(memory_store, world_id, updates, author)
        except Exception:
            # Never raise, record the outcome: a raise would leave `memory_updates` queued in
            # the checkpoint and the next turn would gate stale values against its own message.
            log.exception("remember: the memory store failed")
            results = [unavailable(u) for u in updates]
        return {
            "memory_updates": None,
            "messages": with_turn(
                [
                    HumanMessage(
                        name="memory",
                        # Key only for a refused value; the full notes are in additional_kwargs.
                        content="\n".join(agent_note(r) for r in results),
                        additional_kwargs={"memory": [r.model_dump() for r in results]},
                    )
                ],
                config,
            ),
        }

    return remember


# ---------- check ----------


def _failed_result(p: Proposal) -> CheckResult:
    title = p.after.title if p.after else (p.before.title if p.before else "")
    return CheckResult(
        proposal_id=p.proposal_id,
        verdict="failed",
        flags=[
            Flag(
                kind="note",
                entry_id=p.entry_id or "",
                title=title,
                severity="note",
                explanation=CHECK_FAILED_EXPLANATION,
            )
        ],
    )


def make_check_node(store, model_for: ModelFor):
    async def check(state: SagaState) -> dict:
        judge = model_for("judge")
        checks = state.get("check_results") or {}
        results: dict[str, CheckResult] = {}
        for p in state.get("pending_proposals") or []:
            if p.proposal_id in checks:
                continue
            try:
                results[p.proposal_id] = await check_proposal(store, p, judge)
            except Exception:  # fail closed (R11.3.7): a result is always recorded
                log.exception("check failed for %s", p.proposal_id)
                results[p.proposal_id] = _failed_result(p)
        return {"check_results": results}

    return check


# ---------- approval gate ----------


def _parse_decisions(
    answer: Any, asked: list[Proposal], checks: dict[str, CheckResult]
) -> list[Decision]:
    """Validate the resume value. Raises ValueError (nothing is applied) when malformed."""
    if not isinstance(answer, dict) or not isinstance(answer.get("decisions"), list):
        raise ValueError('Resume with {"decisions": [...]}')
    try:
        decisions = [Decision.model_validate(d) for d in answer["decisions"]]
    except ValidationError as e:
        first = e.errors()[0]
        field = ".".join(str(p) for p in first["loc"])
        where = f" ({field})" if field else ""
        raise ValueError(f"Invalid decision{where}: {first['msg']}") from e
    by_id = {p.proposal_id: p for p in asked}
    given = [d.proposal_id for d in decisions]
    if len(given) != len(set(given)) or set(given) != set(by_id):
        raise ValueError(f"Give exactly one decision for each of: {', '.join(sorted(by_id))}")
    for d in decisions:
        p = by_id[d.proposal_id]
        if d.action == "edit" and (d.edited is None or p.action == "delete"):
            raise ValueError(f"Edit of {p.proposal_id} needs an edited entry (not allowed for delete)")
        if d.action == "save_as_myth" and (p.after is None or p.proposal_id not in checks):
            raise ValueError(f"Save as myth is not possible for {p.proposal_id}")
    return decisions


def approval_gate(state: SagaState) -> Command[Literal["check", "commit"]]:
    """One interrupt for every undecided proposal (R18.5). Edits go back to check (R18.4)."""
    checks = state.get("check_results") or {}
    decided = state.get("decisions") or {}
    asked = [p for p in state.get("pending_proposals") or [] if p.proposal_id not in decided]
    if not asked:
        return Command(goto="commit")
    if any(p.proposal_id not in checks for p in asked):
        return Command(goto="check")  # never show a card without its check result

    payload = {
        "proposals": [p.model_dump(mode="json") for p in asked],
        "checks": {p.proposal_id: checks[p.proposal_id].model_dump(mode="json") for p in asked},
    }
    # A malformed resume must not raise: LangGraph keeps the resume value, so raising would
    # replay the same bad value on every later resume. Instead ask again, with the reason.
    error: str | None = None
    while True:
        answer = interrupt({**payload, "error": error} if error else payload)
        try:
            decisions = _parse_decisions(answer, asked, checks)
            break
        except ValueError as e:
            error = str(e)

    by_id = {p.proposal_id: p for p in asked}
    replaced: list[Proposal] = []
    stale: dict[str, None] = {}
    kept: dict[str, Decision] = {}
    for d in decisions:
        p = by_id[d.proposal_id]
        if d.action == "edit":
            # The edited draft comes from the client: provenance stays the server's (R2.S).
            keep = {k: getattr(p.after, k) for k in PROVENANCE_FIELDS}
            replaced.append(p.model_copy(update={"after": d.edited.model_copy(update=keep)}))
            stale[p.proposal_id] = None
        elif d.action == "save_as_myth":
            # The proposal, not the thread, says whether it came from an import: an `import_wiki`
            # merge on a chat thread keeps its section, an agent-written body never does.
            after = apply_save_as_myth(p, checks[p.proposal_id], d.told_by, imported=p.imported)
            replaced.append(p.model_copy(update={"after": after}))
            stale[p.proposal_id] = None
        else:
            kept[p.proposal_id] = d
    return Command(
        goto="check" if stale else "commit",
        update={"pending_proposals": replaced, "check_results": stale, "decisions": kept},
    )


# ---------- commit ----------


class _CommitFailed(Exception):
    pass


# `commit` is a sync node, so LangGraph runs it in an executor thread. Two threads (chat tabs) on
# the same world can commit at once: the lock makes "pick the next id, then upsert" and "re-read,
# compare versions, then write" atomic, so neither a create nor an update is silently overwritten.
_COMMIT_LOCK = threading.Lock()


def conflict_reason(e: VersionConflictError) -> str:
    """The only writer of the commit conflict copy, for the node's own checks and the store's."""
    if e.actual is None:
        return f"entry {e.entry_id} no longer exists"
    if e.expected == 0:
        return f"an entry with id {e.entry_id} already exists; propose it again"
    return f"entry changed since it was checked (v{e.expected} → v{e.actual}); propose it again"


def _apply(store, p: Proposal) -> str:
    with _COMMIT_LOCK:
        try:
            return _apply_locked(store, p)
        except VersionConflictError as e:  # the node's own check, or the store's guard
            raise _CommitFailed(conflict_reason(e)) from e


def _apply_locked(store, p: Proposal) -> str:
    pid = p.proposal_id
    if p.action == "create":
        if p.after is None:
            raise _CommitFailed("the proposal has no entry")
        entry_id = store.next_entry_id(p.world_id)
        entry = Entry(id=entry_id, world_id=p.world_id, version=1, **p.after.model_dump())
        saved = store.upsert_entry(entry, expected_version=0)
        return f"Review: {pid} approved, committed as {saved.id} (v{saved.version})."

    if not p.entry_id:
        raise _CommitFailed("the proposal has no entry")
    current = store.get_entry(p.world_id, p.entry_id)
    if current is None:
        raise VersionConflictError(p.entry_id, p.before.version if p.before else 0, None)
    if p.before is not None and current.version != p.before.version:
        # Approved against a stale `before`: writing it would undo the other change unflagged.
        raise VersionConflictError(current.id, p.before.version, current.version)
    if p.action == "delete":
        store.delete_entry(p.world_id, current.id)
        return f"Review: {pid} approved, deleted {current.id}."
    if p.after is None:
        raise _CommitFailed("the proposal has no entry")
    entry = Entry.model_validate(
        {
            **current.model_dump(),
            **p.after.model_dump(),
            **merge_provenance(current, p.after),  # the guard
            "version": current.version + 1,  # created_at is kept; upsert refreshes updated_at
        }
    )
    saved = store.upsert_entry(entry, expected_version=current.version)
    return f"Review: {pid} approved, committed as {saved.id} (v{saved.version})."


def make_commit_node(store):
    def commit(state: SagaState, config: RunnableConfig | None = None) -> dict:
        world_id = state.get("world_id")
        checks = state.get("check_results") or {}
        decisions = state.get("decisions") or {}
        messages: list[HumanMessage] = []
        handled: list[str] = []
        refused: list[str] = []
        for p in state.get("pending_proposals") or []:
            pid = p.proposal_id
            d = decisions.get(pid)
            if d is not None and d.action == "reject":
                handled.append(pid)
                messages.append(
                    _review(
                        f"Review: {pid} rejected by the author. Do not propose it again.", pid, "rejected"
                    )
                )
                continue
            if p.world_id != world_id:
                # Nothing is written. The proposal stays pending and must be decided again.
                log.error("commit refused %s: proposed in another world", pid)
                refused.append(pid)
                messages.append(
                    _review(
                        f"Review: {pid} was not committed: it was proposed in another world.",
                        pid,
                        "refused",
                    )
                )
                continue
            if d is None or d.action != "approve" or pid not in checks:
                # R18.3: nothing is written. The proposal stays pending and must be decided again.
                log.error("commit refused %s: not checked and approved", pid)
                refused.append(pid)
                messages.append(
                    _review(
                        f"Review: {pid} was not committed: it has not been checked and approved.",
                        pid,
                        "refused",
                    )
                )
                continue
            handled.append(pid)
            try:
                messages.append(_review(_apply(store, p), pid, "approved"))
            except (DuplicateTitleError, _CommitFailed) as e:
                messages.append(
                    _review(
                        f"Review: {pid} approved, but the commit failed: {e}. Nothing was written.",
                        pid,
                        "failed",
                    )
                )
            except Exception as e:
                log.exception("commit of %s failed", pid)
                messages.append(
                    _review(
                        f"Review: {pid} approved, but the commit failed: {e}. Nothing was written.",
                        pid,
                        "failed",
                    )
                )
        cleared = {pid: None for pid in handled}
        return {
            "messages": with_turn(messages, config),
            "pending_proposals": {"clear": handled},
            "check_results": cleared,
            "decisions": {**cleared, **{pid: None for pid in refused}},
        }

    return commit
