"""Developer settings over HTTP (R12.4)."""

from fakes import KEY

from sagaloom.graph.prompts import SYSTEM


async def test_get_returns_defaults(make_env):
    env = make_env()
    r = await env.client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["settings"] == {
        "agent_temperature": 0.0,
        "agent_max_tokens": None,
        "agent_system_prompt": None,
        "guard_enabled": True,
        "enabled_tools": None,
    }
    assert body["defaults"]["agent_system_prompt"] == SYSTEM
    assert "guard_policy" in body
    assert KEY not in r.text


async def test_put_persists(make_env):
    env = make_env()
    r = await env.client.put("/api/settings", json={"agent_temperature": 0.7})
    assert r.status_code == 200
    assert r.json()["settings"]["agent_temperature"] == 0.7
    assert (await env.client.get("/api/settings")).json()["settings"]["agent_temperature"] == 0.7
    assert KEY not in r.text


async def test_put_rejects_out_of_range(make_env):
    env = make_env()
    assert (await env.client.put("/api/settings", json={"agent_temperature": 5})).status_code == 422


async def test_put_rejects_uneditable_field(make_env):
    env = make_env()
    assert (await env.client.put("/api/settings", json={"judge_temperature": 0.5})).status_code == 422


async def test_settings_need_the_secret(make_env):
    env = make_env()
    assert (await env.client.get("/api/settings", headers={"x-sagaloom-secret": "nope"})).status_code == 401


async def test_put_needs_the_secret(make_env):
    env = make_env()
    r = await env.client.put("/api/settings", json={"agent_temperature": 0.5}, headers={"x-sagaloom-secret": "nope"})
    assert r.status_code == 401


async def test_put_null_clears_max_tokens(make_env):
    env = make_env()
    await env.client.put("/api/settings", json={"agent_max_tokens": 512})
    r = await env.client.put("/api/settings", json={"agent_max_tokens": None})
    assert r.status_code == 200
    assert r.json()["settings"]["agent_max_tokens"] is None
    assert (await env.client.get("/api/settings")).json()["settings"]["agent_max_tokens"] is None


async def test_put_null_temperature_rejected(make_env):
    env = make_env()
    assert (await env.client.put("/api/settings", json={"agent_temperature": None})).status_code == 422


async def test_put_null_guard_enabled_rejected(make_env):
    env = make_env()
    assert (await env.client.put("/api/settings", json={"guard_enabled": None})).status_code == 422


async def test_guard_log_lists_guard_records_newest_first(make_env):
    import json

    from sagaloom.promptlog import PromptRecord

    env = make_env()

    def rec(id, role, at, response, thread="t1"):
        return PromptRecord(
            id=id, thread_id=thread, run_id="r", provider="openrouter", model="google/gemma", role=role,
            request={"messages": [], "tools": []}, response=response, started_at=at,
        )

    log = env.deps.promptlog
    log.add(rec("a", "guard", "2026-01-01T00:00:01", {"content": json.dumps({"verdict": "safe", "reason": "fine"}), "tool_calls": []}))
    log.add(rec("b", "agent", "2026-01-01T00:00:02", {"content": "hi", "tool_calls": []}))
    log.add(rec("c", "guard", "2026-01-01T00:00:03", {"content": "", "tool_calls": [{"id": "1", "name": "GuardVerdict", "args": {"verdict": "injection", "reason": "override"}}]}, thread="t2"))
    log.add(rec("d", "guard", "2026-01-01T00:00:04", {"content": "prose", "tool_calls": []}))
    log.add(rec("e", "router", "2026-01-01T00:00:05", {"content": json.dumps({"mode": "query"}), "tool_calls": []}))
    r = await env.client.get("/api/guard/log?limit=10")
    assert r.status_code == 200
    rows = r.json()
    assert [(x["thread_id"], x["verdict"]) for x in rows] == [("t1", "unknown"), ("t2", "injection"), ("t1", "safe")]
    assert rows[1]["reason"] == "override"
    assert rows[0]["model"] == "google/gemma" and rows[0]["started_at"]
    assert len((await env.client.get("/api/guard/log?limit=1")).json()) == 1


async def test_put_enabled_tools_and_unknown_tool_422(make_env):
    env = make_env()
    r = await env.client.put("/api/settings", json={"enabled_tools": ["export_world"]})
    assert r.status_code == 200 and r.json()["settings"]["enabled_tools"] == ["export_world"]
    assert (await env.client.put("/api/settings", json={"enabled_tools": ["nope"]})).status_code == 422
    r = await env.client.put("/api/settings", json={"enabled_tools": None})
    assert r.json()["settings"]["enabled_tools"] is None


async def test_guard_log_marks_a_failed_call_error(make_env):
    import json

    from sagaloom.promptlog import PromptRecord

    env = make_env()

    def rec(id, at, response):
        return PromptRecord(
            id=id, thread_id="t1", run_id="r", provider="openrouter", model="google/gemma", role="guard",
            request={"messages": [], "tools": []}, response=response, started_at=at,
        )

    log = env.deps.promptlog
    log.add(rec("a", "2026-01-01T00:00:01", None))  # the call raised: no response was recorded
    log.add(rec("b", "2026-01-01T00:00:02", {"content": "prose", "tool_calls": []}))
    log.add(rec("c", "2026-01-01T00:00:03", {"content": json.dumps({"verdict": "safe", "reason": "ok"}), "tool_calls": []}))
    rows = (await env.client.get("/api/guard/log")).json()
    assert [(x["verdict"], x["reason"]) for x in rows] == [("safe", "ok"), ("unknown", ""), ("error", "")]
