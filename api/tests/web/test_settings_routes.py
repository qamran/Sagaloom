"""Developer settings over HTTP (R12.4)."""

from fakes import KEY, TOKEN_B, USER_A, USER_B

from sagaloom.graph.prompts import SYSTEM
from sagaloom.web.access import ADMIN_ONLY


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
        "monthly_budget_usd": 1.0,
    }
    assert body["defaults"]["agent_system_prompt"] == SYSTEM
    assert "guard_policy" in body
    assert KEY not in r.text


async def test_put_persists(make_env):
    env = make_env(admin=True)
    r = await env.client.put("/api/settings", json={"agent_temperature": 0.7})
    assert r.status_code == 200
    assert r.json()["settings"]["agent_temperature"] == 0.7
    assert (await env.client.get("/api/settings")).json()["settings"]["agent_temperature"] == 0.7
    assert KEY not in r.text


async def test_put_rejects_out_of_range(make_env):
    env = make_env(admin=True)
    assert (await env.client.put("/api/settings", json={"agent_temperature": 5})).status_code == 422


async def test_put_rejects_uneditable_field(make_env):
    env = make_env(admin=True)
    assert (await env.client.put("/api/settings", json={"judge_temperature": 0.5})).status_code == 422


async def test_settings_need_the_secret(make_env):
    env = make_env()
    assert (await env.client.get("/api/settings", headers={"x-sagaloom-secret": "nope"})).status_code == 401


async def test_put_needs_the_secret(make_env):
    env = make_env()
    r = await env.client.put("/api/settings", json={"agent_temperature": 0.5}, headers={"x-sagaloom-secret": "nope"})
    assert r.status_code == 401


async def test_put_null_clears_max_tokens(make_env):
    env = make_env(admin=True)
    await env.client.put("/api/settings", json={"agent_max_tokens": 512})
    r = await env.client.put("/api/settings", json={"agent_max_tokens": None})
    assert r.status_code == 200
    assert r.json()["settings"]["agent_max_tokens"] is None
    assert (await env.client.get("/api/settings")).json()["settings"]["agent_max_tokens"] is None


async def test_put_null_clears_system_prompt(make_env):
    env = make_env(admin=True)
    await env.client.put("/api/settings", json={"agent_system_prompt": "x"})
    assert (await env.client.get("/api/settings")).json()["settings"]["agent_system_prompt"] == "x"
    r = await env.client.put("/api/settings", json={"agent_system_prompt": None})
    assert r.status_code == 200
    assert r.json()["settings"]["agent_system_prompt"] is None
    assert (await env.client.get("/api/settings")).json()["settings"]["agent_system_prompt"] is None
    assert env.deps.dev_settings.get().agent_system_prompt is None


async def test_put_null_temperature_rejected(make_env):
    env = make_env(admin=True)
    assert (await env.client.put("/api/settings", json={"agent_temperature": None})).status_code == 422


async def test_put_null_guard_enabled_rejected(make_env):
    env = make_env(admin=True)
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
    log.add(rec("a", "guard", "2026-01-01T00:00:01", {"content": json.dumps({"verdict": "safe", "reason": "fine"}), "tool_calls": []}), user_id="user_a")
    log.add(rec("b", "agent", "2026-01-01T00:00:02", {"content": "hi", "tool_calls": []}), user_id="user_a")
    log.add(rec("c", "guard", "2026-01-01T00:00:03", {"content": "", "tool_calls": [{"id": "1", "name": "GuardVerdict", "args": {"verdict": "injection", "reason": "override"}}]}, thread="t2"), user_id="user_a")
    log.add(rec("d", "guard", "2026-01-01T00:00:04", {"content": "prose", "tool_calls": []}), user_id="user_a")
    log.add(rec("e", "router", "2026-01-01T00:00:05", {"content": json.dumps({"mode": "query"}), "tool_calls": []}), user_id="user_a")
    r = await env.client.get("/api/guard/log?limit=10")
    assert r.status_code == 200
    rows = r.json()
    assert [(x["thread_id"], x["verdict"]) for x in rows] == [("t1", "unknown"), ("t2", "injection"), ("t1", "safe")]
    assert rows[1]["reason"] == "override"
    assert rows[0]["model"] == "google/gemma" and rows[0]["started_at"]
    assert len((await env.client.get("/api/guard/log?limit=1")).json()) == 1


async def test_put_enabled_tools_and_unknown_tool_422(make_env):
    env = make_env(admin=True)
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
    log.add(rec("a", "2026-01-01T00:00:01", None), user_id="user_a")  # the call raised: no response was recorded
    log.add(rec("b", "2026-01-01T00:00:02", {"content": "prose", "tool_calls": []}), user_id="user_a")
    log.add(rec("c", "2026-01-01T00:00:03", {"content": json.dumps({"verdict": "safe", "reason": "ok"}), "tool_calls": []}), user_id="user_a")
    rows = (await env.client.get("/api/guard/log")).json()
    assert [(x["verdict"], x["reason"]) for x in rows] == [("safe", "ok"), ("unknown", ""), ("error", "")]


# ---- M5: admin-only writes, per-user guard log (spec §5.2, §5.5) ----


def _guard_rec(id, at, thread):
    import json

    from sagaloom.promptlog import PromptRecord

    return PromptRecord(
        id=id, thread_id=thread, run_id="r", provider="openrouter", model="google/gemma", role="guard",
        request={"messages": [], "tools": []},
        response={"content": json.dumps({"verdict": "safe", "reason": id}), "tool_calls": []},
        started_at=at,
    )


async def test_guard_log_is_mine(make_env):
    env = make_env(admin=True)
    log = env.deps.promptlog
    log.add(_guard_rec("a1", "2026-01-01T00:00:01", "ta"), user_id=USER_A)
    log.add(_guard_rec("b1", "2026-01-01T00:00:02", "tb"), user_id=USER_B)
    log.add(_guard_rec("n1", "2026-01-01T00:00:03", "gone"))  # nobody's (thread gone before backfill)
    b = env.as_user(TOKEN_B)
    assert [x["reason"] for x in (await b.get("/api/guard/log")).json()] == ["b1"]
    assert [x["reason"] for x in (await env.client.get("/api/guard/log")).json()] == ["a1"]
    assert [x["reason"] for x in (await env.client.get("/api/guard/log?scope=mine")).json()] == ["a1"]
    # The admin's "All users" view: every verdict, including the ownerless ones.
    rows = (await env.client.get("/api/guard/log?scope=all")).json()
    assert [x["reason"] for x in rows] == ["n1", "b1", "a1"]
    r = await b.get("/api/guard/log?scope=all")
    assert r.status_code == 403 and r.json() == {"detail": ADMIN_ONLY}
    assert (await env.client.get("/api/guard/log?scope=everyone")).status_code == 422


async def test_non_admin_settings_write_403(make_env):
    env = make_env()
    before = env.deps.dev_settings.get()
    for body in ({"agent_temperature": 0.7}, {"monthly_budget_usd": 50}, {"agent_temperature": 99}, {"nope": 1}):
        r = await env.client.put("/api/settings", json=body)
        # 403 before validation: a non-admin learns nothing about the body.
        assert r.status_code == 403 and r.json() == {"detail": ADMIN_ONLY}, (body, r.text)
    for body in ({"role": "judge", "model": "openai/gpt-6.1-terra"}, {"role": "judge"}):
        r = await env.client.put("/api/settings/models", json=body)
        assert r.status_code == 403 and r.json() == {"detail": ADMIN_ONLY}, (body, r.text)
    assert env.deps.dev_settings.get() == before
    assert env.deps.model_settings.get_model_settings()["judge"] != "openai/gpt-6.1-terra"
    # Reading stays open to everyone.
    assert (await env.client.get("/api/settings")).status_code == 200
    assert (await env.client.get("/api/settings/models")).status_code == 200


async def test_admin_can_set_budget(make_env):
    env = make_env(admin=True)
    r = await env.client.put("/api/settings", json={"monthly_budget_usd": 2.5})
    assert r.status_code == 200 and r.json()["settings"]["monthly_budget_usd"] == 2.5
    assert (await env.client.get("/api/settings")).json()["settings"]["monthly_budget_usd"] == 2.5
    assert env.deps.dev_settings.get().monthly_budget_usd == 2.5
    for bad in (-1, 1000.01, None):
        r = await env.client.put("/api/settings", json={"monthly_budget_usd": bad})
        assert r.status_code == 422, bad
    assert (await env.client.put("/api/settings", json={"monthly_budget_usd": 0})).status_code == 200
