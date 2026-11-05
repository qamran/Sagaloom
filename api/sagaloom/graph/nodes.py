"""Graph nodes (R18). Only `commit` writes to the store, and it refuses anything that has
not been checked and approved (R18.3)."""

import logging
import threading
from collections.abc import Callable
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.graph import END
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt
from pydantic import ValidationError

from sagaloom.check.contradiction import check_proposal
from sagaloom.check.myth import apply_save_as_myth
from sagaloom.graph.prompts import SYSTEM
from sagaloom.graph.state import Role, SagaState
from sagaloom.guard import BLOCK_COPY, classify
from sagaloom.models import PROVENANCE_FIELDS, CheckResult, Decision, Entry, Flag, Proposal
from sagaloom.provenance import merge_provenance
from sagaloom.settings_store import DevSettings, enabled_tool_names
from sagaloom.store.canon import DuplicateTitleError
from sagaloom.text import message_text

log = logging.getLogger(__name__)

ModelFor = Callable[[Role], BaseChatModel]


class RoleModel:
    """Resolves `model_for(role)` on every use, so a per-role model switch takes effect on
    the next call even though the tools are built once."""

    def __init__(self, model_for: ModelFor, role: Role):
        self._model_for = model_for
        self._role = role

    def __getattr__(self, name: str) -> Any:
        return getattr(self._model_for(self._role), name)


def _review(text: str) -> HumanMessage:
    return HumanMessage(name="review", content=text)


# ---------- routing ----------


def route_after_agent(state: SagaState) -> Literal["tools", "__end__"]:
    msgs = state.get("messages") or []
    last = msgs[-1] if msgs else None
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


def route_after_tools(state: SagaState) -> Literal["check", "agent"]:
    """Any proposal not yet checked AND decided goes to `check` (and from there the gate)."""
    checks = state.get("check_results") or {}
    decisions = state.get("decisions") or {}
    for p in state.get("pending_proposals") or []:
        if p.proposal_id not in checks or p.proposal_id not in decisions:
            return "check"
    return "agent"


def route_after_guard(state: SagaState) -> Literal["agent", "__end__"]:
    return "agent" if state.get("guard_verdict") in ("safe", "off") else END


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

    async def guard(state: SagaState) -> dict:
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
                AIMessage(name="guard", content=BLOCK_COPY[verdict]),
            ],
        }

    return guard


# ---------- agent ----------


def make_agent_node(
    model_for: ModelFor, tools: list[BaseTool], dev: Callable[[], DevSettings] = DevSettings
):
    async def agent(state: SagaState, config: RunnableConfig) -> dict:
        d = dev()  # read every turn, so a settings change applies from the next one
        params: dict[str, Any] = {"temperature": d.agent_temperature}
        if d.agent_max_tokens:
            params["max_tokens"] = d.agent_max_tokens
        enabled = enabled_tool_names(d)
        bound = [t for t in tools if t.name in enabled]
        llm = model_for("agent").bind_tools(bound).bind(**params)
        system = SystemMessage(content=d.agent_system_prompt or SYSTEM)
        reply = await llm.ainvoke([system, *state.get("messages", [])], config)
        return {"messages": [reply]}

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
        enabled = enabled_tool_names(dev())  # read every turn, like the agent node
        msgs = list(state.get("messages") or [])
        last = msgs[-1] if msgs else None
        calls = list(getattr(last, "tool_calls", None) or [])
        if all(c["name"] in enabled for c in calls):
            return await inner.ainvoke(state, config)
        kept = [c for c in calls if c["name"] in enabled]
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
            if c["name"] in enabled:
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
                explanation="The check could not run. Review this change carefully before approving it.",
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
        raise ValueError(f"Invalid decision: {e.errors()[0]['msg']}") from e
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
            after = apply_save_as_myth(p, checks[p.proposal_id], d.told_by)
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


def _apply(store, p: Proposal) -> str:
    with _COMMIT_LOCK:
        return _apply_locked(store, p)


def _apply_locked(store, p: Proposal) -> str:
    pid = p.proposal_id
    if p.action == "create":
        if p.after is None:
            raise _CommitFailed("the proposal has no entry")
        entry_id = store.next_entry_id()
        entry = Entry(id=entry_id, world_id=p.world_id, version=1, **p.after.model_dump())
        saved = store.upsert_entry(entry)
        return f"Review: {pid} approved, committed as {saved.id} (v{saved.version})."

    current = store.get_entry(p.world_id, p.entry_id) if p.entry_id else None
    if current is None:
        raise _CommitFailed(f"entry {p.entry_id} no longer exists")
    if p.before is not None and current.version != p.before.version:
        # Approved against a stale `before`: writing it would undo the other change unflagged.
        raise _CommitFailed(
            f"entry changed since it was checked (v{p.before.version} → v{current.version}); "
            "propose it again"
        )
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
    saved = store.upsert_entry(entry)
    return f"Review: {pid} approved, committed as {saved.id} (v{saved.version})."


def make_commit_node(store):
    def commit(state: SagaState) -> dict:
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
                messages.append(_review(f"Review: {pid} rejected by the author. Do not propose it again."))
                continue
            if d is None or d.action != "approve" or pid not in checks or p.world_id != world_id:
                # R18.3: nothing is written. The proposal stays pending and must be decided again.
                log.error("commit refused %s: not checked and approved", pid)
                refused.append(pid)
                messages.append(
                    _review(f"Review: {pid} was not committed: it has not been checked and approved.")
                )
                continue
            handled.append(pid)
            try:
                messages.append(_review(_apply(store, p)))
            except (DuplicateTitleError, _CommitFailed) as e:
                messages.append(
                    _review(f"Review: {pid} approved, but the commit failed: {e}. Nothing was written.")
                )
            except Exception as e:
                log.exception("commit of %s failed", pid)
                messages.append(
                    _review(f"Review: {pid} approved, but the commit failed: {e}. Nothing was written.")
                )
        cleared = {pid: None for pid in handled}
        return {
            "messages": messages,
            "pending_proposals": {"clear": handled},
            "check_results": cleared,
            "decisions": {**cleared, **{pid: None for pid in refused}},
        }

    return commit
