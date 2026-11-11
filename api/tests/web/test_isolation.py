"""Owner-scoped routes (M5 spec §5.2): a user reaches only the worlds they own, and the threads,
entries, imports and memory inside them. "Not found" and "not yours" both answer 404, so ids
cannot be probed. The admin is not exempt (sharing is a later milestone)."""

import pytest
from fastapi import APIRouter, Depends, Request

from fakes import TOKEN_B, USER_B, W, create_call
from sagaloom.auth import ClerkProfile
from sagaloom.models import Entry
from sagaloom.web.access import ADMIN_ONLY, current_user, require_admin

WB = "wb"  # user B's own world
ENTRY = "ent_0001"

# Every route with `{world_id}` or `{thread_id}` in its path, keyed by (method, path), with the
# request B sends against A's resources. Valid bodies and params, so a 404 is the owner check and
# not a validation error. `test_every_id_route_is_owner_scoped` fails when a new id route is
# added without a row here.
ID_ROUTES: dict[tuple[str, str], dict] = {
    ("GET", "/api/worlds/{world_id}/entries"): {},
    ("GET", "/api/worlds/{world_id}/entries/{entry_id}"): {},
    ("GET", "/api/worlds/{world_id}/entries/{entry_id}/mentions"): {},
    ("GET", "/api/worlds/{world_id}/export"): {"params": {"format": "md"}},
    ("POST", "/api/worlds/{world_id}/imports"): {"json": {"text": "Ostra is a deep-water port."}},
    ("GET", "/api/worlds/{world_id}/memory"): {},
    ("DELETE", "/api/worlds/{world_id}/memory"): {"params": {"key": "tone"}},
    ("GET", "/api/threads/{thread_id}"): {},
    ("POST", "/api/threads/{thread_id}/messages"): {"json": {"content": "Add Ostra"}},
    ("POST", "/api/threads/{thread_id}/decisions"): {"json": {"decisions": []}},
    ("GET", "/api/threads/{thread_id}/runs/last"): {},
    ("GET", "/api/threads/{thread_id}/llm-log"): {},
}


async def two_users(make_env):
    """A owns `W` with an entry and a thread holding a pending approval; B owns `WB`."""
    env = make_env([create_call()])
    env.deps.store.upsert_entry(Entry(id=ENTRY, world_id=W, title="Velmar", type="place", body="A city."))
    env.deps.worlds.create("B's World", world_id=WB, owner_id=USER_B)
    tid = await env.new_thread(W)
    r, _ = await env.send(tid)
    assert r.status_code == 200
    assert (await env.client.get(f"/api/threads/{tid}")).json()["pending_interrupt"] is not None
    return env, tid, env.as_user(TOKEN_B)


def _url(path: str, tid: str) -> str:
    return path.format(world_id=W, thread_id=tid, entry_id=ENTRY)


@pytest.mark.parametrize("method,path", sorted(ID_ROUTES))
async def test_other_users_id_routes_are_404(make_env, method, path):
    env, tid, b = await two_users(make_env)
    before = (env.deps.threads.list(W), env.deps.threads.get(tid).summary)
    assert before[1] is not None  # so "summary not cleared" below can fail
    r = await b.request(method, _url(path, tid), **ID_ROUTES[(method, path)])
    assert r.status_code == 404, r.text
    # Nothing changed for A: no new thread in A's world, A's thread summary not cleared.
    assert (env.deps.threads.list(W), env.deps.threads.get(tid).summary) == before
    # Control: the same request as A is not a 404, so the 404 above is the owner check.
    mine = await env.client.request(method, _url(path, tid), **ID_ROUTES[(method, path)])
    assert mine.status_code != 404, mine.text


def test_every_id_route_is_owner_scoped(make_env):
    env = make_env()
    # Read from the OpenAPI schema: FastAPI 0.162 keeps included routers nested in `app.routes`
    # (as private `_IncludedRouter`s), and the schema lists every route of the whole app.
    id_routes = {
        (method.upper(), path)
        for path, ops in env.app.openapi()["paths"].items()
        if "{world_id}" in path or "{thread_id}" in path
        for method in ops
    }
    assert len(id_routes) >= 12  # the schema really lists the routes
    assert id_routes == set(ID_ROUTES), "every id route needs a row in ID_ROUTES"


async def test_create_thread_in_other_users_world_is_404(make_env):
    env, _, b = await two_users(make_env)
    before = env.deps.threads.list(W)
    r = await b.post("/api/threads", json={"world_id": W})
    assert r.status_code == 404
    assert env.deps.threads.list(W) == before
    assert (await b.post("/api/threads", json={"world_id": WB})).status_code == 200


async def test_lists_hold_only_own_worlds_and_threads(make_env):
    env, tid, b = await two_users(make_env)
    b_tid = (await b.post("/api/threads", json={"world_id": WB})).json()["thread_id"]
    assert [w["id"] for w in (await b.get("/api/worlds")).json()] == [WB]
    assert [w["id"] for w in (await env.client.get("/api/worlds")).json()] == [W]
    assert [t["thread_id"] for t in (await b.get("/api/threads")).json()] == [b_tid]
    assert (await b.get("/api/threads", params={"pending": "true"})).json() == []
    assert [t["thread_id"] for t in (await env.client.get("/api/threads")).json()] == [tid]
    mine = (await env.client.get("/api/threads", params={"pending": "true"})).json()
    assert [t["thread_id"] for t in mine] == [tid]


async def test_thread_list_filtered_by_other_users_world_is_empty(make_env):
    # A list filter, not an id route: a foreign world_id answers an empty list, not 404.
    env, tid, b = await two_users(make_env)
    for params in ({"world_id": W}, {"world_id": W, "pending": "true"}, {"world_id": "ghost"}):
        r = await b.get("/api/threads", params=params)
        assert r.status_code == 200 and r.json() == [], params
    r = await env.client.get("/api/threads", params={"world_id": W})
    assert [t["thread_id"] for t in r.json()] == [tid]


async def test_create_world_belongs_to_creator(make_env):
    env, _, b = await two_users(make_env)
    r = await b.post("/api/worlds", json={"name": "Ostra Sea"})
    assert r.status_code == 200 and r.json()["owner_id"] == USER_B
    assert env.deps.worlds.get("ostra-sea").owner_id == USER_B
    assert [w["id"] for w in (await env.client.get("/api/worlds")).json()] == [W]
    assert (await env.client.get("/api/worlds/ostra-sea/entries")).status_code == 404


async def test_ownerless_world_is_nobodys(make_env):
    env = make_env()
    env.deps.worlds.create("Orphan", world_id="orphan")
    tid = env.deps.threads.create("orphan")
    assert [w["id"] for w in (await env.client.get("/api/worlds")).json()] == [W]
    assert (await env.client.get("/api/worlds/orphan/entries")).status_code == 404
    assert (await env.client.get(f"/api/threads/{tid}")).status_code == 404
    assert (await env.client.get("/api/threads")).json() == []


async def test_thread_of_a_missing_world_is_404(make_env):
    env = make_env()
    tid = env.deps.threads.create("ghost")
    assert (await env.client.get(f"/api/threads/{tid}")).status_code == 404


def _sign_in_admin(env) -> None:
    env.deps.settings.admin_email = "boss@example.test"
    env.deps.verifier.tokens["tok-boss"] = "user_boss"
    env.deps.directory.profiles["user_boss"] = ClerkProfile(
        email="boss@example.test", email_verified=True, display_name="Boss"
    )


async def test_admin_is_not_exempt(make_env):
    env, tid, _ = await two_users(make_env)
    _sign_in_admin(env)
    boss = env.as_user("tok-boss")
    assert (await boss.get(f"/api/worlds/{W}/entries")).status_code == 404
    assert (await boss.get(f"/api/threads/{tid}")).status_code == 404
    assert (await boss.get("/api/worlds")).json() == []
    assert (await boss.get("/api/threads")).json() == []


async def test_require_admin(make_env):
    env = make_env()
    _sign_in_admin(env)
    probe = APIRouter(prefix="/api", dependencies=[Depends(current_user)])

    @probe.get("/_admin_only")
    async def admin_only(request: Request):
        return {"id": require_admin(request).id}

    env.app.include_router(probe)
    r = await env.client.get("/api/_admin_only")
    assert r.status_code == 403 and r.json() == {"detail": ADMIN_ONLY}
    assert ADMIN_ONLY == "Only the admin can change developer settings."
    r = await env.as_user("tok-boss").get("/api/_admin_only")
    assert r.status_code == 200 and r.json() == {"id": "user_boss"}
