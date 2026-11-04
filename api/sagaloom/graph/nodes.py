"""Graph nodes (R18). Only `commit` writes to the store, and it refuses anything that has
not been checked and approved (R18.3)."""

import logging
from collections.abc import Callable
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.graph import END
from langgraph.types import Command, interrupt
from pydantic import ValidationError

from sagaloom.check.contradiction import check_proposal
from sagaloom.check.myth import apply_save_as_myth
from sagaloom.config import Settings
from sagaloom.graph.prompts import SYSTEM
from sagaloom.graph.state import Role, SagaState
from sagaloom.models import CheckResult, Decision, Entry, Flag, Proposal
from sagaloom.store.canon import DuplicateTitleError
from sagaloom.usage import extract_usage

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


# ---------- agent ----------


def make_agent_node(model_for: ModelFor, tools: list[BaseTool], settings: Settings):
    async def agent(state: SagaState, config: RunnableConfig) -> dict:
        llm = model_for("agent").bind_tools(tools)
        reply = await llm.ainvoke([SystemMessage(content=SYSTEM), *state.get("messages", [])], config)
        return {"messages": [reply], "token_usage": extract_usage(reply, settings)}

    return agent


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
            replaced.append(p.model_copy(update={"after": d.edited}))
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


def _apply(store, p: Proposal) -> str:
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
    if p.action == "delete":
        store.delete_entry(p.world_id, current.id)
        return f"Review: {pid} approved, deleted {current.id}."
    if p.after is None:
        raise _CommitFailed("the proposal has no entry")
    entry = Entry.model_validate(
        {
            **current.model_dump(),
            **p.after.model_dump(),
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
