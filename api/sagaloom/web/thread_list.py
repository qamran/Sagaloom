"""`GET /threads` without a checkpoint read per thread (M3 #73, plan ruling R5).

Each registry row carries a summary of its thread (pending count, worst badge, outcomes, derived
title). A turn clears it when it takes the thread's lock, and writes it again from one
`aget_state` just before its terminal `done` or `error`. A row with no summary (pre-M3 data, or a
turn cut off at shutdown) is read once and filled lazily. A running thread is always read live,
and that read is never stored.
"""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from typing import Any, cast

from langchain_core.messages import HumanMessage

from sagaloom.check.badge import Badge, with_badges, worst_badge
from sagaloom.store.threads import ThreadInfo, ThreadKind, ThreadSummary
from sagaloom.text import message_text
from sagaloom.web.sse import Event

log = logging.getLogger(__name__)

TITLE_CHARS = 80
TERMINAL = frozenset({"done", "error"})


def pending_interrupt(state) -> dict | None:
    """The pending interrupt, each check with its badge (derived here, so a checkpoint written
    before badges existed still shows them)."""
    return with_badges(dict(state.interrupts[0].value)) if state.interrupts else None


def outcomes(messages: list) -> tuple[int, int]:
    """(approved, rejected), counted from the review notes' `outcome`; a note without one (written
    before outcomes existed), a failed write and a refused commit count as neither."""
    found = [
        m.additional_kwargs.get("outcome")
        for m in messages
        if isinstance(m, HumanMessage) and m.name == "review"
    ]
    return found.count("approved"), found.count("rejected")


def thread_title(title: str | None, messages: list) -> str | None:
    """The registry title, else the author's first message on one line, cut to TITLE_CHARS."""
    if title:
        return title
    first = next((m for m in messages if isinstance(m, HumanMessage) and not m.name), None)
    if first is None:
        return None
    text = " ".join(message_text(first.content).split())
    return text if len(text) <= TITLE_CHARS else text[: TITLE_CHARS - 1] + "…"


def summarise(state, title: str | None) -> ThreadSummary:
    """One thread's list summary from its checkpoint state. Pure."""
    interrupt = pending_interrupt(state)
    checks = interrupt["checks"].values() if interrupt else []
    messages = (state.values or {}).get("messages") or []
    approved, rejected = outcomes(messages)
    return ThreadSummary(
        pending=len(interrupt["proposals"]) if interrupt else 0,
        badge=worst_badge(c["badge"] for c in checks),
        approved=approved,
        rejected=rejected,
        title=thread_title(title, messages),
    )


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


async def refresh_summary(deps: Any, thread_id: str) -> None:
    """Writes the thread's summary from one checkpoint read. A row that is gone (a failed import)
    is left alone; a failed read is logged and leaves the summary unset for the lazy fill."""
    try:
        info = deps.threads.get(thread_id)
        if info is None:
            return
        state = await deps.graph.aget_state(_config(thread_id))
        deps.threads.set_summary(thread_id, summarise(state, info.title))
    except Exception:
        log.exception("refresh_summary: could not summarise thread %s", thread_id)


async def with_summary(
    events: AsyncIterator[Event], refresh: Callable[[], Awaitable[None]]
) -> AsyncIterator[Event]:
    """`events`, with `refresh()` awaited before the terminal `done` or `error` is passed on (or
    at the end, if neither comes), so a client that reads `done` and lists threads sees the new
    summary. A cancelled stream (shutdown) does not refresh: the summary stays unset."""
    refreshed = False
    async with aclosing(events) as stream:
        async for ev in stream:
            if ev["event"] in TERMINAL and not refreshed:
                refreshed = True
                await refresh()
            yield ev
    if not refreshed:
        await refresh()


def _running(deps: Any, thread_id: str) -> bool:
    lock = deps.locks.get(thread_id)
    return lock is not None and lock.locked()


def _row(t: ThreadInfo, s: ThreadSummary, running: bool) -> dict:
    return {
        "thread_id": t.thread_id,
        "world_id": t.world_id,
        "pending": s.pending,
        "created_at": t.created_at,
        "kind": t.kind,
        # The registry title wins at read time, so one set after the summary still shows.
        "title": t.title or s.title,
        "badge": cast(Badge | None, s.badge),
        "approved": s.approved,
        "rejected": s.rejected,
        "running": running,
    }


async def list_rows(
    deps: Any, *, pending: bool, world_id: str | None, kind: ThreadKind | None
) -> list[dict]:
    """Newest first. `badge` is the worst badge among the pending checks, `running` whether the
    thread's turn lock is held. A summarised thread that is not running costs no checkpoint read."""
    out = []
    for t in reversed(deps.threads.list(world_id, kind)):
        running = _running(deps, t.thread_id)
        if t.summary is not None and not running:
            summary = t.summary
        else:
            try:
                state = await deps.graph.aget_state(_config(t.thread_id))
                summary = summarise(state, t.title)
            except Exception:
                # One unreadable checkpoint must not take the whole list down.
                log.exception("list_threads: unreadable checkpoint %s", t.thread_id)
                continue
            was_running, running = running, _running(deps, t.thread_id)
            # No await between this check and the write: a turn that took the lock meanwhile
            # has cleared the summary, and a read from before it must not fill it. A turn that
            # took and released the lock within this read cannot be overwritten either: it
            # stored its own summary before releasing, so `set_summary_if_unset` writes nothing.
            if not was_running and not running:
                try:
                    deps.threads.set_summary_if_unset(t.thread_id, summary)
                except Exception:
                    # A best-effort cache write: the row was read, so it still lists.
                    log.exception("list_threads: could not store summary %s", t.thread_id)
        if pending and not summary.pending:
            continue
        out.append(_row(t, summary, running))
    return out
