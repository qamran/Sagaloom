"""`GET/PUT /api/me` (M5 spec §5.4, §5.5a): the signed-in account, its spend this month and its
last world."""

from datetime import UTC, datetime

from fakes import TOKEN_B, USER_A, USER_B, W

from sagaloom.promptlog import PromptRecord

WB = "wb"


def _spend(env, id: str, at: str, cost: float, user: str = USER_A) -> None:
    env.deps.promptlog.add(
        PromptRecord(
            id=id, thread_id="t", run_id="r", provider="openrouter", model="m", role="agent",
            request={"messages": [], "tools": []},
            response={"prompt_tokens": 1, "completion_tokens": 1, "cost_usd": cost},
            started_at=at,
        ),
        user_id=user,
    )


async def test_me_shape(make_env):
    env = make_env()
    env.deps.now = lambda: datetime(2026, 11, 11, 16, 37, tzinfo=UTC)
    _spend(env, "oct", "2026-10-31T23:59:59+00:00", 0.5)
    _spend(env, "nov", "2026-11-02T10:00:00+00:00", 0.23)
    _spend(env, "b", "2026-11-03T10:00:00+00:00", 0.4, user=USER_B)
    r = await env.client.get("/api/me")
    assert r.status_code == 200
    body = r.json()
    assert body.pop("month_spend_usd") == 0.23
    assert body == {
        "id": USER_A,
        "email": "user_a@example.test",
        "display_name": USER_A,
        "is_admin": False,
        "last_world_id": None,
        "monthly_budget_usd": 1.0,
        "budget_resets_on": "2026-12-01",
        "over_budget": False,
    }
    env.deps.now = lambda: datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
    body = (await env.client.get("/api/me")).json()
    assert (body["month_spend_usd"], body["budget_resets_on"]) == (0.0, "2027-01-01")


async def test_me_budget_follows_settings_and_admin_is_unlimited(make_env):
    from sagaloom.settings_store import DevSettingsPatch

    env = make_env(admin=True)
    env.deps.dev_settings.update(DevSettingsPatch(monthly_budget_usd=3))
    admin = (await env.client.get("/api/me")).json()
    assert admin["is_admin"] is True and admin["monthly_budget_usd"] is None
    other = (await env.as_user(TOKEN_B).get("/api/me")).json()
    assert other["is_admin"] is False and other["monthly_budget_usd"] == 3.0


async def test_put_me_sets_last_world(make_env):
    env = make_env()
    r = await env.client.put("/api/me", json={"last_world_id": W})
    assert r.status_code == 200 and r.json()["last_world_id"] == W
    assert env.deps.users.get(USER_A).last_world_id == W
    assert (await env.client.get("/api/me")).json()["last_world_id"] == W
    r = await env.client.put("/api/me", json={"last_world_id": None})
    assert r.status_code == 200 and r.json()["last_world_id"] is None
    assert env.deps.users.get(USER_A).last_world_id is None


async def test_put_me_rejects_foreign_world(make_env):
    env = make_env()
    env.deps.worlds.create("B's World", world_id=WB, owner_id=USER_B)
    await env.client.put("/api/me", json={"last_world_id": W})
    for world_id in (WB, "no-such-world"):
        r = await env.client.put("/api/me", json={"last_world_id": world_id})
        assert r.status_code == 404, world_id
    assert env.deps.users.get(USER_A).last_world_id == W  # unchanged
    assert (await env.client.put("/api/me", json={})).status_code == 422
    assert (await env.client.put("/api/me", json={"last_world_id": W, "is_admin": True})).status_code == 422


async def test_me_needs_sign_in(make_env):
    env = make_env()
    env.client.headers.pop("Authorization")
    assert (await env.client.get("/api/me")).status_code == 401
    assert (await env.client.put("/api/me", json={"last_world_id": W})).status_code == 401


async def test_me_over_budget_flag(make_env):
    """`over_budget` is the server's `spend >= budget` rule (M5 spec §5.5a): the UI swaps the
    composer for the 402 message without doing the sum itself. Never true for the admin."""
    from sagaloom.settings_store import DevSettingsPatch

    env = make_env(admin=True)
    env.deps.now = lambda: datetime(2026, 11, 11, 16, 37, tzinfo=UTC)
    _spend(env, "a", "2026-11-02T10:00:00+00:00", 50.0)  # the admin's spend: no limit
    _spend(env, "b1", "2026-11-02T10:00:00+00:00", 0.6, user=USER_B)
    b = env.as_user(TOKEN_B)
    assert (await env.client.get("/api/me")).json()["over_budget"] is False
    assert (await b.get("/api/me")).json()["over_budget"] is False
    _spend(env, "b2", "2026-11-03T10:00:00+00:00", 0.4, user=USER_B)  # exactly the budget
    assert (await b.get("/api/me")).json()["over_budget"] is True
    assert (await b.put("/api/me", json={"last_world_id": None})).json()["over_budget"] is True
    env.deps.dev_settings.update(DevSettingsPatch(monthly_budget_usd=2))
    assert (await b.get("/api/me")).json()["over_budget"] is False
