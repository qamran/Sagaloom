"""The SSE events of one import (R3.1, R3.2, R18.10): extraction, then the graph run from `check`.

Extraction reports through the existing event set (`node` and `tool_result`, both named
`extract`), and the extractor's prompt records arrive as `llm_request`/`llm_response` while it
runs. A wiki import first reports its page requests the same way (`node` and `tool_result`, both
named `fetch`). The graph run then streams as any turn does, and its `done` carries the new
`thread_id`.

When the extraction fails entirely, or a wiki's licence can't be read, the graph never runs: the
stream ends with `usage` (the extractor's spend, which the PromptLog has counted), then `error`,
and no `done`. These are the only places a failed stream still sends `usage`; a failed graph run
ends with `error` alone, as R19.2 says.
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from typing import Any

from langchain_core.messages import HumanMessage

from sagaloom.importing.extract import ImportPlan, build_import
from sagaloom.importing.wiki import (
    LICENCE_UNREADABLE,
    NOTE_CONTENT,
    build_wiki_import,
    fetch_wiki,
    licence_dict,
)
from sagaloom.models import Usage
from sagaloom.web.sse import Event, drain, event, run_turn_events
from sagaloom.wiki.client import LicenceUnreadable, WikiClient
from sagaloom.wiki.pages import WikiPage

log = logging.getLogger(__name__)

EXTRACTION_FAILED = "The extraction could not run, so nothing was imported. Try again."

UsageFn = Callable[[], tuple[Usage, Usage]]


def import_note(plan: ImportPlan, label: str) -> HumanMessage:
    """The note that opens an import thread. Its `content` is neutral: candidate titles and
    excerpts are untrusted, so they live only in `additional_kwargs` and the proposals (R-W5-4)."""
    return HumanMessage(
        name="import",
        content=(
            f"Imported text: {len(plan.proposals)} proposals for review, "
            f"{len(plan.skipped)} not imported."
        ),
        additional_kwargs={
            "import": {
                "kind": "text",
                "source": label,
                "first_lines": dict(plan.first_lines),
                "skipped": [s.model_dump() for s in plan.skipped],
            }
        },
    )


def wiki_note(plan: ImportPlan, host: str) -> HumanMessage:
    """The note that opens a wiki import thread. Its `content` holds counts only: page titles and
    text are untrusted, so they live in `additional_kwargs` and the proposals (R-W5-4)."""
    return HumanMessage(
        name="import",
        content=NOTE_CONTENT.format(len(plan.proposals), len(plan.skipped)),
        additional_kwargs={
            "import": {
                "kind": "wiki",
                "source": host,
                "licence": dict(plan.licence or {}),
                "first_lines": dict(plan.first_lines),
                "skipped": [s.model_dump() for s in plan.skipped],
            }
        },
    )


async def _extraction(
    job: asyncio.Future, queue: asyncio.Queue
) -> AsyncIterator[Event]:
    """The queued prompt events as they arrive while `job` runs, then whatever is left."""
    while not job.done():
        getter = asyncio.ensure_future(queue.get())
        try:
            done, _ = await asyncio.wait({job, getter}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            if not getter.done():
                getter.cancel()
        if getter in done:
            yield getter.result()
    for ev in drain(queue):
        yield ev


def _usage(usage_fn: UsageFn) -> Event:
    turn, total = usage_fn()
    return event("usage", {"turn": turn.model_dump(), "total": total.model_dump()})


async def _run_graph(
    graph: Any,
    world_id: str,
    thread_id: str,
    plan: ImportPlan,
    note: HumanMessage,
    cfg: dict,
    queue: asyncio.Queue,
    usage_fn: UsageFn,
) -> AsyncIterator[Event]:
    """The graph run from `check` on the plan's proposals, opened by the import note; its `done`
    carries the thread id."""
    run_input = {
        "entry": "import",
        "world_id": world_id,
        "pending_proposals": plan.proposals,
        "messages": [note],
    }
    async for ev in run_turn_events(graph, run_input, cfg, extra=queue, usage_fn=usage_fn):
        yield event("done", {"thread_id": thread_id}) if ev["event"] == "done" else ev


async def _extract_then_run(
    graph: Any,
    build: Callable[[], Awaitable[ImportPlan]],
    note: Callable[[ImportPlan], HumanMessage],
    world_id: str,
    thread_id: str,
    cfg: dict,
    queue: asyncio.Queue,
    usage_fn: UsageFn,
    registry: Any,
) -> AsyncIterator[Event]:
    """The run tail every import shares: `node extract start`, the extractor's prompt events while
    `build()` runs, `tool_result extract`, `node extract end`, then the graph run; or, when every
    part failed, `usage` and `error`."""
    yield event("node", {"name": "extract", "phase": "start"})
    t0 = time.monotonic()
    job = asyncio.ensure_future(build())
    try:
        # Closed as soon as this stream is, not whenever the loop finalises it (Wave 5 M12).
        async with aclosing(_extraction(job, queue)) as stream:
            async for ev in stream:
                yield ev
    except asyncio.CancelledError:
        # Shut down before any plan existed: the graph never ran, so no row stays behind (R-W5-5).
        registry.delete(thread_id)
        raise
    finally:
        if not job.done():
            job.cancel()
    plan: ImportPlan | None = None
    try:
        plan = job.result()
    except Exception:
        log.exception("import extraction failed")
    candidates, skipped = (len(plan.proposals), len(plan.skipped)) if plan else (0, 0)
    yield event(
        "tool_result",
        {
            "name": "extract",
            "summary": f"{candidates} candidates, {skipped} not imported",
            "candidates": candidates,
            "skipped": skipped,
        },
    )
    yield event("node", {"name": "extract", "phase": "end", "ms": int((time.monotonic() - t0) * 1000)})

    if plan is None or (plan.parts > 0 and plan.failed_parts == plan.parts):
        # Nothing was imported and the graph never ran, so no checkpoint exists (R-W5-5). The
        # extractor's calls were still paid for, so `usage` comes before the `error`. A plan with
        # no parts (wiki pages with no article text) still runs, so Review shows its note.
        registry.delete(thread_id)
        yield _usage(usage_fn)
        yield event("error", {"message": EXTRACTION_FAILED, "retryable": True})
        return

    async for ev in _run_graph(graph, world_id, thread_id, plan, note(plan), cfg, queue, usage_fn):
        yield ev


async def import_events(
    graph: Any,
    store: Any,
    extractor: Any,
    world_id: str,
    thread_id: str,
    text: str,
    label: str,
    cfg: dict,
    queue: asyncio.Queue,
    usage_fn: UsageFn,
    registry: Any,
) -> AsyncIterator[Event]:
    # The turn's config, so the extractor call is logged under this turn (usage, drawer).
    tail = _extract_then_run(
        graph,
        lambda: build_import(store, extractor, world_id, text, label, cfg),
        lambda plan: import_note(plan, label),
        world_id,
        thread_id,
        cfg,
        queue,
        usage_fn,
        registry,
    )
    async with aclosing(tail) as stream:
        async for ev in stream:
            yield ev


async def wiki_import_events(
    graph: Any,
    store: Any,
    client: WikiClient,
    extractor: Any,
    world_id: str,
    thread_id: str,
    pages: list[WikiPage],
    cfg: dict,
    queue: asyncio.Queue,
    usage_fn: UsageFn,
    registry: Any,
) -> AsyncIterator[Event]:
    """`node fetch`, `tool_result fetch` and `node fetch end` around the page requests, then the
    shared run tail. An unreadable licence ends the stream after `node fetch end` with `usage` and
    `error`, before any page was requested. When no page was fetched, extraction is skipped and the
    graph runs with the note alone, so Review lists every page with its reason."""
    host = pages[0].host
    yield event("node", {"name": "fetch", "phase": "start"})
    t0 = time.monotonic()
    fetched = None
    try:
        fetched = await fetch_wiki(client, pages)
    except LicenceUnreadable:
        log.info("wiki import: the licence of %s could not be read", host)
    except BaseException:
        # Shut down (or failed) before any plan existed: the graph never ran, so no row stays.
        registry.delete(thread_id)
        raise
    if fetched is not None:
        k, j = len(fetched.pages), len(fetched.skipped)
        yield event(
            "tool_result",
            {"name": "fetch", "summary": f"{k} pages fetched, {j} not fetched", "pages": k, "failed": j},
        )
    yield event("node", {"name": "fetch", "phase": "end", "ms": int((time.monotonic() - t0) * 1000)})

    if fetched is None:
        registry.delete(thread_id)
        yield _usage(usage_fn)
        yield event("error", {"message": LICENCE_UNREADABLE.format(host=host), "retryable": True})
        return

    if not fetched.pages:
        plan = ImportPlan(
            proposals=[],
            skipped=fetched.skipped,
            first_lines={},
            failed_parts=0,
            parts=0,
            licence=licence_dict(fetched.licence),
        )
        tail = _run_graph(graph, world_id, thread_id, plan, wiki_note(plan, host), cfg, queue, usage_fn)
    else:
        tail = _extract_then_run(
            graph,
            lambda: build_wiki_import(store, extractor, world_id, fetched, cfg),
            lambda plan: wiki_note(plan, host),
            world_id,
            thread_id,
            cfg,
            queue,
            usage_fn,
            registry,
        )
    async with aclosing(tail) as stream:
        async for ev in stream:
            yield ev
