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
