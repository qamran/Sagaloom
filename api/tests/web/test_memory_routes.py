"""GET/DELETE /api/worlds/{id}/memory, the memory role in thread history, and the SSE note
(R10.2, R19.1, spec §3.5)."""

from langchain_core.messages import AIMessage, HumanMessage

from sagaloom.memory import apply_updates
from sagaloom.models import MemoryUpdate
from sagaloom.web.routes import message_dict

from fakes import HEADERS, W

DEMO = "Remember: keep the tone grim, and I never want chosen-one prophecies."


def empty_payload(threads: int = 0) -> dict:
    return {
        "preferences": {},
        "count": 0,
        "cap": 20,
        "short_term": {"threads": threads, "checkpoint_file": "data/checkpoints.sqlite"},
    }


async def seed_prefs(env) -> None:
    updates = [
        MemoryUpdate(key="tone", value="grim"),
        MemoryUpdate(key="banned_tropes", value="chosen-one prophecies"),
        MemoryUpdate(key="banned_tropes", value="grim"),
    ]
    results = await apply_updates(env.deps.memory, W, updates, DEMO)
    assert all(r.stored for r in results)


async def test_get_memory_empty_and_counts_this_worlds_threads(make_env):
    env = make_env()
    assert (await env.client.get(f"/api/worlds/{W}/memory")).json() == empty_payload()
    await env.new_thread()
    await env.new_thread()
    env.deps.threads.create("another-world")
    r = await env.client.get(f"/api/worlds/{W}/memory")
    assert r.status_code == 200
    assert r.json() == empty_payload(threads=2)


async def test_get_memory_lists_preferences_and_count(make_env):
    env = make_env()
    await seed_prefs(env)
    body = (await env.client.get(f"/api/worlds/{W}/memory")).json()
    assert body["preferences"] == {"tone": "grim", "banned_tropes": ["chosen-one prophecies", "grim"]}
    assert body["count"] == 3 and body["cap"] == 20


async def test_delete_item_then_key(make_env):
    env = make_env()
    await seed_prefs(env)
    r = await env.client.delete(
        f"/api/worlds/{W}/memory", params={"key": "banned_tropes", "item": "grim"}
    )
    assert r.status_code == 200
    assert r.json()["preferences"] == {"tone": "grim", "banned_tropes": ["chosen-one prophecies"]}
    assert r.json()["count"] == 2
    r = await env.client.delete(f"/api/worlds/{W}/memory", params={"key": "tone"})
    assert r.status_code == 200
    assert r.json()["preferences"] == {"banned_tropes": ["chosen-one prophecies"]}
    assert r.json()["count"] == 1


async def test_delete_is_idempotent_and_validated(make_env):
    env = make_env()
    url = f"/api/worlds/{W}/memory"
    r = await env.client.delete(url, params={"key": "genre"})
    assert r.status_code == 200 and r.json() == empty_payload()
    r = await env.client.delete(url, params={"key": "notes", "item": "never set"})
    assert r.status_code == 200 and r.json() == empty_payload()
    assert (await env.client.delete(url)).status_code == 422
    assert (await env.client.delete(url, params={"key": "mood"})).status_code == 422


async def test_memory_routes_unknown_world_404(make_env):
    env = make_env()
    assert (await env.client.get("/api/worlds/nope/memory")).status_code == 404
    r = await env.client.delete("/api/worlds/nope/memory", params={"key": "tone"})
    assert r.status_code == 404


async def test_memory_routes_need_the_secret(make_env):
    env = make_env()
    r = await env.client.get(f"/api/worlds/{W}/memory", headers={"X-Sagaloom-Secret": "wrong"})
    assert r.status_code == 401
    r = await env.client.delete(
        f"/api/worlds/{W}/memory", params={"key": "tone"}, headers={"X-Sagaloom-Secret": "wrong"}
    )
    assert r.status_code == 401


async def test_cors_allows_delete(make_env):
    env = make_env()
    r = await env.client.options(
        f"/api/worlds/{W}/memory",
        headers={
            "Origin": env.settings.web_origin,
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "x-sagaloom-secret",
        },
    )
    assert r.status_code == 200
    assert "DELETE" in r.headers["access-control-allow-methods"]


def test_message_dict_memory_role():
    items = [{"key": "tone", "value": "grim", "stored": True, "note": "Remembered: tone → grim"}]
    m = HumanMessage(name="memory", content="Remembered: tone → grim", additional_kwargs={"memory": items})
    assert message_dict(m) == {
        "role": "memory",
        "content": "Remembered: tone → grim",
        "name": "memory",
        "memory": items,
    }
    # The author's own message and review notes are unchanged.
    assert message_dict(HumanMessage(content="hi")) == {"role": "user", "content": "hi"}
    assert message_dict(HumanMessage(name="review", content="r"))["role"] == "review"


def remember_call() -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "remember_preference",
                "args": {"key": "tone", "value": "grim"},
                "id": "call_mem",
                "type": "tool_call",
            }
        ],
    )


async def test_turn_streams_remember_result_and_history_shows_it(make_env):
    env = make_env([remember_call(), AIMessage(content="Noted.")])
    tid = await env.new_thread()
    r, events = await env.send(tid, DEMO)
    assert r.status_code == 200
    results = [d for e, d in events if e == "tool_result" and d["name"] == "remember"]
    assert results == [
        {
            "name": "remember",
            "summary": "Remembered: tone → grim",
            "memory": [
                {"key": "tone", "value": "grim", "stored": True, "note": "Remembered: tone → grim"}
            ],
        }
    ]
    assert {e for e, _ in events} <= {
        "token", "tool_call", "tool_result", "node", "llm_request", "llm_response",
        "interrupt", "usage", "done", "error",
    }
    body = (await env.client.get(f"/api/threads/{tid}")).json()
    [mem] = [m for m in body["messages"] if m["role"] == "memory"]
    assert mem["memory"][0]["stored"] is True
    prefs = (await env.client.get(f"/api/worlds/{W}/memory", headers=HEADERS)).json()
    assert prefs["preferences"] == {"tone": "grim"}
