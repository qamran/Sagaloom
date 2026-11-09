"""Turns a graph run into the SSE event stream of R19.2.

Order inside a turn: `node`/`llm_request`/`token`/`tool_call`/`tool_result`/`llm_response` as they
happen, then (if the run paused) `interrupt`, then `usage`, then `done`. A failed run ends with
`error` instead of `usage` and `done`.
"""

import asyncio
import json
import logging
import time
from contextlib import aclosing
from collections.abc import AsyncIterator, Callable
from typing import Any

import openai
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError
from sse_starlette import EventSourceResponse
from starlette.background import BackgroundTask

from sagaloom.check.badge import with_badges
from sagaloom.models import Usage
from sagaloom.text import message_text

log = logging.getLogger(__name__)

MODEL_UNAVAILABLE = "The model service is unavailable right now. Please try again."
TOO_MANY_STEPS = "That took too many steps, so I stopped. Try a simpler request."
UNEXPECTED = "Something went wrong. Please try again."
SUMMARY_CHARS = 300

Event = dict[str, Any]  # {"event": name, "data": dict}


def _ev(name: str, data: dict | None = None) -> Event:
    return {"event": name, "data": data or {}}


def _drain(queue: asyncio.Queue | None) -> list[Event]:
    out: list[Event] = []
    while queue is not None and not queue.empty():
        out.append(queue.get_nowait())
    return out


GEMINI_HOST = "generativelanguage.googleapis.com"
GEMINI_ERRORS = {
    429: "Gemini's free tier is out of requests right now.",
    503: "Gemini is overloaded right now.",
}


def gemini_error_event(exc: Exception) -> dict | None:
    """The error data for a Gemini 429/503, with the offer to go back to OpenRouter; None for
    anything else (including OpenRouter errors)."""
    if not isinstance(exc, openai.APIStatusError) or exc.status_code not in GEMINI_ERRORS:
        return None
    if exc.response.request.url.host != GEMINI_HOST:
        return None
    return {
        "message": GEMINI_ERRORS[exc.status_code],
        "retryable": False,
        "switch_back": "openrouter",
        "switch_back_label": "Switch back to OpenRouter",
    }


def _error_event(exc: Exception) -> Event:
    if isinstance(exc, GraphRecursionError):
        return _ev("error", {"message": TOO_MANY_STEPS, "retryable": False})
    if (gemini := gemini_error_event(exc)) is not None:
        return _ev("error", gemini)
    if isinstance(exc, openai.APIError):  # connection, timeout, status and rate-limit errors
        return _ev("error", {"message": MODEL_UNAVAILABLE, "retryable": True})
    return _ev("error", {"message": UNEXPECTED, "retryable": True})


def _update_events(node: str, upd: Any) -> list[Event]:
    """tool_call / tool_result events found in one node's state update, plus two node-built
    notes: the guard's notice is sent as the turn's `token` (the notice is the reply), and the
    `remember` node's note as a `tool_result` named `remember` carrying its per-preference
    results (the event set stays unchanged)."""
    events: list[Event] = []
    for item in upd if isinstance(upd, list) else [upd]:
        if not isinstance(item, dict):
            continue
        msgs = item.get("messages") or []
        for m in msgs if isinstance(msgs, list) else [msgs]:
            if node == "guard" and isinstance(m, AIMessage) and m.name == "guard":
                if text := message_text(m.content):
                    events.append(_ev("token", {"text": text}))
            elif node == "remember" and isinstance(m, HumanMessage) and m.name == "memory":
                events.append(
                    _ev(
                        "tool_result",
                        {
                            "name": "remember",
                            "summary": message_text(m.content),
                            "memory": list(m.additional_kwargs.get("memory") or []),
                        },
                    )
                )
            elif isinstance(m, AIMessage) and m.tool_calls:
                events += [_ev("tool_call", {"name": c["name"], "args": c["args"]}) for c in m.tool_calls]
            elif isinstance(m, ToolMessage):
                events.append(
                    _ev(
                        "tool_result",
                        {"name": m.name or "", "summary": message_text(m.content)[:SUMMARY_CHARS]},
                    )
                )
    return events


async def run_turn_events(
    graph: Any,
    input_or_command: Any,
    config: dict,
    *,
    extra: asyncio.Queue | None = None,
    usage_fn: Callable[[], tuple[Usage, Usage]],
) -> AsyncIterator[Event]:
    """Run the graph and yield SSE events. `extra` carries events produced outside the graph
    stream (the prompt-capture handler's llm_request / llm_response). `usage_fn` returns
    (turn, total) from the prompt log, which counts every model call (R12)."""
    try:
        started: dict[str, float] = {}
        async for mode, payload in graph.astream(
            input_or_command, config, stream_mode=["messages", "updates", "debug"]
        ):
            for ev in _drain(extra):
                yield ev
            if mode == "messages":
                chunk, meta = payload
                if (
                    isinstance(chunk, (AIMessageChunk, AIMessage))
                    and meta.get("langgraph_node") == "agent"
                    and (text := message_text(chunk.content))
                ):
                    yield _ev("token", {"text": text})
            elif mode == "updates":
                for node, upd in payload.items():
                    if node == "__interrupt__":
                        for it in upd:
                            yield _ev("interrupt", with_badges(dict(it.value)))
                        continue
                    for ev in _update_events(node, upd):
                        yield ev
            elif mode == "debug":
                kind, body = payload.get("type"), payload.get("payload") or {}
                if kind == "task":
                    started[body["id"]] = time.monotonic()
                    yield _ev("node", {"name": body["name"], "phase": "start"})
                elif kind == "task_result":
                    t0 = started.pop(body["id"], None)
                    ms = int((time.monotonic() - t0) * 1000) if t0 is not None else 0
                    yield _ev("node", {"name": body["name"], "phase": "end", "ms": ms})
        for ev in _drain(extra):
            yield ev
        turn, total = usage_fn()
        yield _ev("usage", {"turn": turn.model_dump(), "total": total.model_dump()})
        yield _ev("done")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if not isinstance(exc, (GraphRecursionError, openai.APIError)):
            log.exception("turn failed")
        for ev in _drain(extra):
            yield ev
        yield _error_event(exc)


async def sse_events(events: AsyncIterator[Event]) -> AsyncIterator[dict[str, str]]:
    async for ev in events:
        yield {"event": ev["event"], "data": json.dumps(ev["data"], ensure_ascii=False)}


def sse_response(
    events: AsyncIterator[Event], on_close: Callable[[], None] | None = None
) -> EventSourceResponse:
    """`on_close` always runs once the stream ends, fails, or the client goes away."""

    async def guarded() -> AsyncIterator[dict[str, str]]:
        try:
            async with aclosing(sse_events(events)) as stream:
                async for item in stream:
                    yield item
        finally:
            if on_close:
                on_close()

    return EventSourceResponse(
        guarded(), background=BackgroundTask(on_close) if on_close else None
    )


_END = object()


def shielded(
    events: AsyncIterator[Event], *, on_finish: Callable[[], None], tasks: set[asyncio.Task]
) -> AsyncIterator[Event]:
    """Run `events` to its end in a task of its own, so a client that goes away does not cancel
    the turn (Review Focus 5): the run still reaches its interrupt and is picked up from
    `GET /threads/{id}`. The task starts now (not on the first read), `on_finish` runs once when
    it ends however it ends, and it sits in `tasks` until then (the app cancels those at shutdown).
    The returned generator only reads the queue, so closing it leaves the task running.
    A task cancelled before its first step never runs `pump`, so the done callback also finishes
    (idempotently) and ends the reader."""
    queue: asyncio.Queue = asyncio.Queue()
    finished = False

    def finish() -> None:
        nonlocal finished
        if not finished:
            finished = True
            on_finish()

    async def pump() -> None:
        try:
            async with aclosing(events) as stream:
                async for ev in stream:
                    queue.put_nowait(ev)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("turn stream failed")
            queue.put_nowait(_error_event(exc))
        finally:
            finish()

    def done(_: asyncio.Task) -> None:
        try:
            finish()
        finally:
            queue.put_nowait(_END)

    task = asyncio.get_running_loop().create_task(pump())
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    task.add_done_callback(done)

    async def read() -> AsyncIterator[Event]:
        while (ev := await queue.get()) is not _END:
            yield ev

    return read()
