"""run_turn_events and the SSE framing (R19.2, Review Focus 5)."""

import json

from langchain_core.messages import HumanMessage

from sagaloom.graph.build import run_config
from sagaloom.models import Usage
from sagaloom.web.sse import run_turn_events, sse_events

from fakes import W, create_call


async def test_partial_turn_visible_via_get_after_client_disconnect(make_env):
    env = make_env([create_call()])
    tid = await env.new_thread()
    gen = run_turn_events(
        env.deps.graph,
        {"messages": [HumanMessage(content="Add Ostra")], "world_id": W},
        run_config(tid, W),
        usage_fn=lambda: (Usage(), Usage()),
    )
    async for ev in gen:
        if ev["event"] == "tool_call":
            break
    await gen.aclose()  # the client went away mid-turn
    body = (await env.client.get(f"/api/threads/{tid}")).json()
    assert body["messages"][0] == {"role": "user", "content": "Add Ostra"}


async def test_sse_events_frames_each_event_as_name_plus_json():
    async def events():
        yield {"event": "token", "data": {"text": "hi"}}
        yield {"event": "done", "data": {}}

    out = [e async for e in sse_events(events())]
    assert out == [
        {"event": "token", "data": json.dumps({"text": "hi"})},
        {"event": "done", "data": "{}"},
    ]


async def test_usage_comes_from_usage_fn_only(make_env):
    env = make_env()
    tid = await env.new_thread()
    turn, total = Usage(prompt_tokens=7), Usage(prompt_tokens=9)
    events = [
        ev
        async for ev in run_turn_events(
            env.deps.graph,
            {"messages": [HumanMessage(content="hi")], "world_id": W},
            run_config(tid, W),
            usage_fn=lambda: (turn, total),
        )
    ]
    [usage] = [ev["data"] for ev in events if ev["event"] == "usage"]
    assert usage == {"turn": turn.model_dump(), "total": total.model_dump()}
