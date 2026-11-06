"""The SSE events of one import (R3.1, R3.2, R18.10): extraction, then the graph run from `check`.

Extraction reports through the existing event set (`node` and `tool_result`, both named
`extract`), and the extractor's prompt records arrive as `llm_request`/`llm_response` while it
runs. The graph run then streams as any turn does, and its `done` carries the new `thread_id`.
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from langchain_core.messages import HumanMessage

from sagaloom.importing.extract import ImportPlan, build_import
from sagaloom.models import Usage
from sagaloom.web.sse import Event, _drain, _ev, run_turn_events

log = logging.getLogger(__name__)

EXTRACTION_FAILED = "The extraction could not run, so nothing was imported. Try again."


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
                "source": label,
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
    for ev in _drain(queue):
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
    usage_fn: Callable[[], tuple[Usage, Usage]],
    registry: Any,
) -> AsyncIterator[Event]:
    yield _ev("node", {"name": "extract", "phase": "start"})
    t0 = time.monotonic()
    # The turn's config, so the extractor call is logged under this turn (usage, drawer).
    job = asyncio.ensure_future(build_import(store, extractor, world_id, text, label, cfg))
    try:
        async for ev in _extraction(job, queue):
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
    yield _ev(
        "tool_result",
        {
            "name": "extract",
            "summary": f"{candidates} candidates, {skipped} not imported",
            "candidates": candidates,
            "skipped": skipped,
        },
    )
    yield _ev("node", {"name": "extract", "phase": "end", "ms": int((time.monotonic() - t0) * 1000)})

    if plan is None or plan.failed_parts == plan.parts:
        # Nothing was imported and the graph never ran, so no checkpoint exists (R-W5-5).
        registry.delete(thread_id)
        yield _ev("error", {"message": EXTRACTION_FAILED, "retryable": True})
        return

    run_input = {
        "entry": "import",
        "world_id": world_id,
        "pending_proposals": plan.proposals,
        "messages": [import_note(plan, label)],
    }
    async for ev in run_turn_events(graph, run_input, cfg, extra=queue, usage_fn=usage_fn):
        yield _ev("done", {"thread_id": thread_id}) if ev["event"] == "done" else ev
