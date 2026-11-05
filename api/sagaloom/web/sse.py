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
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langgraph.errors import GraphRecursionError
from sse_starlette import EventSourceResponse
from starlette.background import BackgroundTask

from sagaloom.models import Usage

log = logging.getLogger(__name__)

MODEL_UNAVAILABLE = "The model service is unavailable right now. Please try again."
TOO_MANY_STEPS = "That took too many steps, so I stopped. Try a simpler request."
UNEXPECTED = "Something went wrong. Please try again."
SUMMARY_CHARS = 300

Event = dict[str, Any]  # {"event": name, "data": dict}


def _ev(name: str, data: dict | None = None) -> Event:
    return {"event": name, "data": data or {}}


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b.get("text", "") if isinstance(b, dict) else (b if isinstance(b, str) else "")
            for b in content
        )
    return ""


def _drain(queue: asyncio.Queue | None) -> list[Event]:
    out: list[Event] = []
    while queue is not None and not queue.empty():
        out.append(queue.get_nowait())
    return out


def _error_event(exc: Exception) -> Event:
    if isinstance(exc, GraphRecursionError):
        return _ev("error", {"message": TOO_MANY_STEPS, "retryable": False})
    if isinstance(exc, openai.APIError):  # connection, timeout, status and rate-limit errors
        return _ev("error", {"message": MODEL_UNAVAILABLE, "retryable": True})
    return _ev("error", {"message": UNEXPECTED, "retryable": True})


def _update_events(node: str, upd: Any) -> list[Event]:
    """tool_call / tool_result events found in one node's state update, plus the guard's notice:
    it is built by the guard node rather than streamed by a model, so it arrives here and is
    sent as the turn's `token` (the notice is the reply)."""
    events: list[Event] = []
    for item in upd if isinstance(upd, list) else [upd]:
        if not isinstance(item, dict):
            continue
        msgs = item.get("messages") or []
        for m in msgs if isinstance(msgs, list) else [msgs]:
            if node == "guard" and isinstance(m, AIMessage) and m.name == "guard":
                if text := _text(m.content):
                    events.append(_ev("token", {"text": text}))
            elif isinstance(m, AIMessage) and m.tool_calls:
                events += [_ev("tool_call", {"name": c["name"], "args": c["args"]}) for c in m.tool_calls]
            elif isinstance(m, ToolMessage):
                events.append(
                    _ev(
                        "tool_result",
                        {"name": m.name or "", "summary": _text(m.content)[:SUMMARY_CHARS]},
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
                    and (text := _text(chunk.content))
                ):
                    yield _ev("token", {"text": text})
            elif mode == "updates":
                for node, upd in payload.items():
                    if node == "__interrupt__":
                        for it in upd:
                            yield _ev("interrupt", dict(it.value))
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
