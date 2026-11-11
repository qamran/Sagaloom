"""`GET /api/public/preview` (M5 spec §5.7): frozen Velmar example for logged-out visitors."""

import json

from sagaloom.web.public_routes import PREVIEW_FILE

MAYOR_SECRET = "Yes, at every full Ister"  # the Mayor's secret fact in the Velmar seed


async def test_preview_needs_secret_not_user(make_env):
    env = make_env()
    env.client.headers.pop("Authorization")  # no signed-in user
    r = await env.client.get("/api/public/preview")
    assert r.status_code == 200
    assert env.deps.verifier.calls == 0  # no user check at all
    env.client.headers.pop("X-Sagaloom-Secret")
    r = await env.client.get("/api/public/preview")
    assert r.status_code == 401 and r.json() == {"detail": "unauthorised"}


async def test_preview_is_get_only(make_env):
    env = make_env()
    assert (await env.client.post("/api/public/preview", json={})).status_code == 405
    assert (await env.client.put("/api/public/preview", json={})).status_code == 405


async def test_preview_has_conflict_with_ent_0012(make_env):
    env = make_env()
    data = (await env.client.get("/api/public/preview")).json()
    assert set(data) == {"messages", "pending_interrupt", "entries"}
    assert data["messages"][0] == {
        "role": "user",
        "content": "Velmar has three moons that rise together at the solstice.",
        **{k: v for k, v in data["messages"][0].items() if k not in ("role", "content")},
    }
    checks = data["pending_interrupt"]["checks"]
    assert data["pending_interrupt"]["proposals"]
    assert any(
        c["verdict"] == "conflict" and c["badge"] == "conflict" and any(f["entry_id"] == "ent_0012" for f in c["flags"])
        for c in checks.values()
    )
    assert {"ent_0012"} <= {e["id"] for e in data["entries"]}


async def test_preview_has_no_secrets(make_env):
    env = make_env()
    r = await env.client.get("/api/public/preview")
    data = r.json()
    assert data["entries"]
    for e in data["entries"]:
        assert e["status"] != "secret"
        assert all(f.get("status") != "secret" for f in e["facts"])
    # The served text and the file itself: no secret entry title, no secret fact value.
    for text in (r.text, PREVIEW_FILE.read_text(encoding="utf-8")):
        assert "Choir Ledger" not in text
        assert MAYOR_SECRET not in text


async def test_preview_makes_no_model_call(make_env):
    env = make_env()
    env.deps.graph = None  # the route must not need the graph
    r = await env.client.get("/api/public/preview")
    assert r.status_code == 200
    assert env.agent.seen == []
    assert env.deps.promptlog.month_spend is not None  # sanity: the log exists
    assert json.loads(r.text) == json.loads(PREVIEW_FILE.read_text(encoding="utf-8"))
