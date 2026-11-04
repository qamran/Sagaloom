"""HTTP API tests (R19.1, R5.5, R14, R15 rulings, R16.1, R20.2)."""

import json

from langchain_core.messages import AIMessage

from sagaloom.models import Entry
from sagaloom.seed import VELMAR_ID
from sagaloom.store.worlds import WorldRegistry
from sagaloom.web.app import AppDeps, SEED_DIR

from fakes import KEY, W, create_call, endless, names, parse_sse, tc


def approve(pid):
    return {"proposal_id": pid, "action": "approve"}


# ---------- auth ----------


async def test_thread_routes_need_the_secret(make_env):
    env = make_env()
    env.client.headers.pop("X-Sagaloom-Secret")
    for method, url in [("get", "/api/threads"), ("get", "/api/tools"), ("get", "/api/studio")]:
        assert (await getattr(env.client, method)(url)).status_code == 401
    assert (await env.client.post("/api/threads", json={"world_id": W})).status_code == 401


# ---------- threads ----------


async def test_create_thread_and_get_empty_state(make_env):
    env = make_env()
    tid = await env.new_thread()
    assert len(tid) == 32
    r = await env.client.get(f"/api/threads/{tid}")
    assert r.status_code == 200
    assert r.json() == {
        "thread_id": tid,
        "world_id": W,
        "messages": [],
        "pending_interrupt": None,
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0},
    }
    assert (await env.client.get("/api/threads/nope")).status_code == 404


async def test_message_stream_emits_tokens_tool_events_interrupt_usage_done(make_env):
    env = make_env([create_call()])
    tid = await env.new_thread()
    r, events = await env.send(tid)
    assert r.headers["content-type"].startswith("text/event-stream")
    seq = names(events)
    order = ["token", "tool_call", "tool_result", "interrupt", "usage", "done"]
    idx = [seq.index(n) for n in order]
    assert idx == sorted(idx), seq
    assert seq[-1] == "done"
    assert "".join(d["text"] for e, d in events if e == "token") == "Drafting Ostra now."
    call = next(d for e, d in events if e == "tool_call")
    assert call["name"] == "create_or_update_entry" and call["args"]["title"] == "Ostra"
    result = next(d for e, d in events if e == "tool_result")
    assert result["name"] == "create_or_update_entry" and isinstance(result["summary"], str)
    interrupt = next(d for e, d in events if e == "interrupt")
    [p] = interrupt["proposals"]
    assert p["after"]["title"] == "Ostra" and p["proposal_id"] in interrupt["checks"]
    usage = next(d for e, d in events if e == "usage")
    assert usage["turn"]["prompt_tokens"] == 100 and usage["total"]["prompt_tokens"] == 100


async def test_get_thread_returns_pending_interrupt_after_stream_ends(make_env):
    env = make_env([create_call()])
    tid = await env.new_thread()
    await env.send(tid)
    body = (await env.client.get(f"/api/threads/{tid}")).json()  # R5.5
    [p] = body["pending_interrupt"]["proposals"]
    assert p["after"]["title"] == "Ostra"
    assert set(body["pending_interrupt"]) >= {"proposals", "checks"}
    assert body["usage"]["prompt_tokens"] == 100
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["user", "assistant", "tool"]
    assert body["messages"][0]["content"] == "Add Ostra"
    assert body["messages"][1]["tool_calls"][0]["name"] == "create_or_update_entry"
    assert body["messages"][2]["name"] == "create_or_update_entry"


async def test_messages_while_approval_pending_returns_409(make_env):
    env = make_env([create_call()])
    tid = await env.new_thread()
    await env.send(tid)
    r, _ = await env.send(tid, "ignore that, new topic")
    assert r.status_code == 409 and r.json() == {"detail": "approval pending"}
    body = (await env.client.get(f"/api/threads/{tid}")).json()
    assert body["pending_interrupt"] is not None  # approval still pending, nothing dropped
    assert [m["content"] for m in body["messages"] if m["role"] == "user"] == ["Add Ostra"]


async def test_decisions_resume_and_commit(make_env, store):
    env = make_env([create_call(), AIMessage(content="Saved it.")])
    tid = await env.new_thread()
    await env.send(tid)
    pid = await env.pending_id(tid)
    r, events = await env.decide(tid, approve(pid))
    assert r.status_code == 200
    assert names(events)[-1] == "done" and "usage" in names(events)
    assert [e.title for e in store.list_entries(W)] == ["Ostra"]
    body = (await env.client.get(f"/api/threads/{tid}")).json()
    assert body["pending_interrupt"] is None
    review = [m for m in body["messages"] if m["role"] == "review"]
    assert len(review) == 1 and "committed" in review[0]["content"]
    assert body["messages"][-1] == {"role": "assistant", "content": "Saved it."}


async def test_decisions_without_pending_returns_409(make_env):
    env = make_env()
    tid = await env.new_thread()
    r, _ = await env.decide(tid, approve("p1"))
    assert r.status_code == 409 and r.json() == {"detail": "no pending approval"}


async def test_duplicate_decision_returns_409_and_commits_once(make_env, store):
    env = make_env([create_call(), AIMessage(content="Saved it.")])
    tid = await env.new_thread()
    await env.send(tid)
    pid = await env.pending_id(tid)
    first, _ = await env.decide(tid, approve(pid))
    second, _ = await env.decide(tid, approve(pid))
    assert first.status_code == 200
    assert second.status_code == 409
    assert [e.title for e in store.list_entries(W)] == ["Ostra"]


async def test_decisions_must_name_exactly_the_pending_ids(make_env, store):
    env = make_env([create_call(), AIMessage(content="Saved it.")])
    tid = await env.new_thread()
    await env.send(tid)
    pid = await env.pending_id(tid)
    bad = {
        "unknown": [approve("nope")],
        "extra": [approve(pid), approve("nope")],
        "duplicate": [approve(pid), approve(pid)],
        "missing": [],
    }
    for label, decisions in bad.items():
        r, _ = await env.decide(tid, *decisions)
        assert r.status_code == 422, label
    # nothing was resumed: still pending, canon untouched
    assert (await env.client.get(f"/api/threads/{tid}")).json()["pending_interrupt"] is not None
    assert store.list_entries(W) == []
    ok, _ = await env.decide(tid, approve(pid))
    assert ok.status_code == 200


async def test_pending_threads_listing(make_env):
    env = make_env([create_call()])
    waiting = await env.new_thread()
    idle = await env.new_thread()
    await env.send(waiting)
    r = await env.client.get("/api/threads", params={"pending": "true"})
    assert r.json() == [{"thread_id": waiting, "world_id": W, "pending": 1}]
    everything = {t["thread_id"]: t["pending"] for t in (await env.client.get("/api/threads")).json()}
    assert everything == {waiting: 1, idle: 0}


# ---------- worlds and entries ----------


def _entry(world, eid, title):
    return Entry(id=eid, world_id=world, title=title, type="place", body="b")


async def test_entries_scoped_by_world(make_env, store):
    env = make_env()
    store.upsert_entry(_entry("w1", "ent_0001", "Alpha"))
    store.upsert_entry(_entry("w2", "ent_0002", "Beta"))
    one = (await env.client.get("/api/worlds/w1/entries")).json()
    assert [e["title"] for e in one] == ["Alpha"]
    assert [e["title"] for e in (await env.client.get("/api/worlds/w2/entries")).json()] == ["Beta"]
    assert (await env.client.get("/api/worlds/w1/entries/ent_0001")).json()["title"] == "Alpha"
    assert (await env.client.get("/api/worlds/w1/entries/ent_0002")).status_code == 404  # other world
    assert (await env.client.get("/api/worlds/w1/entries/ent_9999")).status_code == 404


async def test_worlds_create_and_list(make_env):
    env = make_env()
    assert [w["id"] for w in (await env.client.get("/api/worlds")).json()] == [W]
    r = await env.client.post("/api/worlds", json={"name": "Ostra Sea"})
    assert r.status_code == 200 and r.json()["id"] == "ostra-sea" and r.json()["name"] == "Ostra Sea"
    assert [w["id"] for w in (await env.client.get("/api/worlds")).json()] == [W, "ostra-sea"]
    assert (await env.client.post("/api/worlds", json={"name": ""})).status_code == 422


async def test_thread_for_unknown_world_is_rejected(make_env):
    env = make_env()
    r = await env.client.post("/api/threads", json={"world_id": "ghost"})
    assert r.status_code == 404


# ---------- errors (R16.1, R15) ----------


async def test_llm_failure_emits_friendly_error_event(make_env):
    import httpx
    import openai

    boom = openai.APIConnectionError(request=httpx.Request("POST", "https://openrouter.ai/x"))
    env = make_env([boom])
    tid = await env.new_thread()
    r, events = await env.send(tid)
    assert r.status_code == 200
    err = [d for e, d in events if e == "error"]
    assert err == [
        {"message": "The model service is unavailable right now. Please try again.", "retryable": True}
    ]
    assert "Traceback" not in r.text and "openrouter.ai" not in r.text
    assert "done" not in names(events)


async def test_recursion_limit_becomes_error_event(make_env):
    env = make_env(endless(lambda: tc("search_canon", {"query": "x"})))
    tid = await env.new_thread()
    r, events = await env.send(tid)
    err = [d for e, d in events if e == "error"]
    assert err == [
        {"message": "That took too many steps, so I stopped. Try a simpler request.", "retryable": False}
    ]


# ---------- tools, studio ----------


async def test_tools_endpoint_lists_three_core_tools(make_env):
    env = make_env()
    tools = (await env.client.get("/api/tools")).json()
    assert {t["name"] for t in tools} == {"search_canon", "create_or_update_entry", "check_contradiction"}
    assert all(t["description"] for t in tools)


async def test_studio_stub(make_env):
    env = make_env()
    body = (await env.client.get("/api/studio")).json()
    assert body["features"] == [] and body["providers"] == []
    assert set(body["usage"]) == {"prompt_tokens", "completion_tokens", "cost_usd"}


# ---------- prompt capture over HTTP (R20.1, R20.2) ----------


async def test_stream_emits_node_and_llm_events_per_model_call(make_env):
    env = make_env([create_call(), AIMessage(content="Saved it.")])
    tid = await env.new_thread()
    _, events = await env.send(tid)
    nodes = [(d["name"], d["phase"]) for e, d in events if e == "node"]
    assert nodes[0] == ("agent", "start") and ("agent", "end") in nodes
    assert ("tools", "start") in nodes and ("check", "end") in nodes
    assert all("ms" in d for e, d in events if e == "node" and d["phase"] == "end")
    seq = names(events)
    assert seq.count("llm_request") == 1 and seq.count("llm_response") == 1
    assert seq.index("llm_request") < seq.index("token") < seq.index("llm_response")
    req = next(d for e, d in events if e == "llm_request")
    assert req["messages"][0]["role"] == "system"
    assert [m["role"] for m in req["messages"][1:]] == ["user"]
    resp = next(d for e, d in events if e == "llm_response")
    assert resp["tool_calls"][0]["name"] == "create_or_update_entry"
    assert resp["prompt_tokens"] == 100 and resp["completion_tokens"] == 20
    # the second turn (resume) makes a second model call
    pid = await env.pending_id(tid)
    _, more = await env.decide(tid, approve(pid))
    assert names(more).count("llm_request") == 1 and names(more).count("llm_response") == 1


async def test_llm_log_survives_refresh_and_never_contains_api_key(make_env):
    env = make_env([create_call(), AIMessage(content="Saved it.")])
    tid = await env.new_thread()
    r1, events = await env.send(tid, f"Add Ostra. My key is {KEY} by the way")
    pid = await env.pending_id(tid)
    r2, more = await env.decide(tid, approve(pid))
    streamed = [d for e, d in events + more if e == "llm_request"]
    log = await env.client.get(f"/api/threads/{tid}/llm-log")
    records = log.json()
    assert len(records) == len(streamed) == 2
    assert [r["request"]["messages"] for r in records] == [
        [{k: v for k, v in m.items()} for m in s["messages"]] for s in streamed
    ]
    assert all(r["response"] is not None and r["thread_id"] == tid for r in records)
    assert records[0]["model"] and records[0]["request"]["messages"][0]["role"] == "system"
    # "refresh": a brand-new log object over the same file returns the same thing
    from sagaloom.promptlog import PromptLog

    assert len(PromptLog(env.deps.promptlog.path).list(tid)) == 2
    everything = log.text + r1.text + r2.text
    assert KEY not in everything
    assert (await env.client.get("/api/threads/nope/llm-log")).status_code == 404


# ---------- startup ----------


async def test_startup_seeds_velmar_once(store, tmp_path, make_env):
    env = make_env()
    deps = AppDeps(
        store=store,
        worlds=WorldRegistry(tmp_path / "fresh-worlds.json"),
        threads=env.deps.threads,
        graph=env.deps.graph,
        settings=env.settings,
        promptlog=env.deps.promptlog,
        seed_dir=SEED_DIR,
    )
    from sagaloom.web.app import create_app

    app = create_app(env.settings, deps)
    for _ in range(2):
        async with app.router.lifespan_context(app):
            pass
    assert [w.id for w in deps.worlds.list()] == [VELMAR_ID]
    n = len(store.list_entries(VELMAR_ID))
    assert n > 0
    async with app.router.lifespan_context(app):
        pass
    assert len(store.list_entries(VELMAR_ID)) == n
