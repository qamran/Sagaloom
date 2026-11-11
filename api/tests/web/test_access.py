"""`current_user`: every /api route but health needs the shared secret AND a verified Clerk user."""

import logging

from fastapi import APIRouter, Depends, Request
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage

from fakes import TOKEN_A, USER_A, W, bearer, names
from sagaloom.accounts import ensure_user
from sagaloom.auth import AuthError, Claims, ClerkDirectory, ClerkProfile
from sagaloom.config import Settings
from sagaloom.web.access import current_user, user_of
from sagaloom.web.app import AppDeps, create_app


async def test_no_token_401(make_env):
    env = make_env()
    env.client.headers.pop("Authorization")
    r = await env.client.get("/api/worlds")
    assert r.status_code == 401 and r.json() == {"detail": "sign in required"}


async def test_bad_token_401(make_env, caplog):
    env = make_env()
    caplog.set_level(logging.DEBUG)
    for header in ("Bearer tok-unknown", "Basic tok-a", "Bearer", "tok-a"):
        r = await env.client.get("/api/worlds", headers={"Authorization": header})
        assert r.status_code == 401 and r.json() == {"detail": "sign in required"}, header
    assert "tok-unknown" not in caplog.text and "DecodeError" not in caplog.text


async def test_valid_token_sets_user(make_env):
    env = make_env()
    # A probe under the same dependency reads the user the way a route will.
    probe = APIRouter(prefix="/api", dependencies=[Depends(current_user)])

    @probe.get("/_whoami")
    async def whoami(request: Request):
        user = user_of(request)
        return {"id": user.id, "email": user.email, "is_admin": user.is_admin}

    env.app.include_router(probe)
    r = await env.client.get("/api/_whoami")
    assert r.status_code == 200
    assert r.json() == {"id": USER_A, "email": "user_a@example.test", "is_admin": False}
    stored = env.deps.users.get(USER_A)
    assert stored is not None and stored.display_name == USER_A
    # The profile is fetched from Clerk only when the user row is new.
    assert (await env.client.get("/api/_whoami")).status_code == 200
    assert env.deps.directory.fetched == [USER_A]


async def test_valid_token_on_a_real_route_creates_the_user(make_env):
    env = make_env()
    assert (await env.client.get("/api/worlds")).status_code == 200
    assert env.deps.users.get(USER_A) is not None


async def test_admin_flag_from_verified_admin_email(make_env):
    env = make_env()
    env.deps.settings.admin_email = "Boss@Example.test"
    env.deps.verifier.tokens["tok-boss"] = "user_boss"
    env.deps.directory.profiles["user_boss"] = ClerkProfile(
        email="boss@example.test", email_verified=True, display_name="Boss"
    )
    boss = await ensure_user(env.deps, Claims(sub="user_boss"))
    assert boss.is_admin is True
    a = await ensure_user(env.deps, Claims(sub=USER_A))
    assert a.is_admin is False


async def test_secret_still_required(make_env):
    env = make_env()
    env.client.headers.pop("X-Sagaloom-Secret")
    r = await env.client.get("/api/worlds")
    assert r.status_code == 401 and r.json() == {"detail": "unauthorised"}
    assert env.deps.verifier.calls == 0  # the secret is checked first


async def test_health_needs_nothing(make_env):
    env = make_env()
    env.client.headers.clear()
    r = await env.client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


async def test_as_user_signs_in_another_user(make_env):
    env = make_env()
    env.deps.verifier.tokens["tok-b"] = "user_b"
    b = env.as_user("tok-b")
    assert (await b.get("/api/worlds")).status_code == 200
    assert env.deps.users.get("user_b") is not None


async def test_stream_outlives_token_expiry(make_env):
    env = make_env([AIMessage(content="Just chatting.")])
    tid = await env.new_thread(W)
    # From here `tok-a` is accepted once more (the message POST), then it has expired.
    env.deps.verifier.calls = 0
    env.deps.verifier.expire_after = 1
    r, events = await env.send(tid, "hello")
    assert r.status_code == 200 and names(events)[-1] == "done", names(events)
    expired = await env.client.get("/api/worlds")
    assert expired.status_code == 401 and expired.json() == {"detail": "sign in required"}


async def test_unconfigured_issuer_rejects_every_token_and_logs_once(store, tmp_path, caplog):
    settings = Settings(_env_file=None, openrouter_api_key="k", api_shared_secret="s", data_dir=tmp_path)
    assert settings.clerk_issuer is None
    deps = AppDeps(store=store, graph="graph", seed_dir=None)
    app = create_app(settings, deps)
    caplog.set_level(logging.ERROR)
    async with app.router.lifespan_context(app):
        pass
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR and "CLERK_ISSUER" in r.getMessage()]
    assert len(errors) == 1

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/worlds", headers={"X-Sagaloom-Secret": "s", **bearer(TOKEN_A)})
    assert r.status_code == 401 and r.json() == {"detail": "sign in required"}


async def test_lifespan_builds_and_closes_the_clerk_directory(store, tmp_path):
    settings = Settings(
        _env_file=None, openrouter_api_key="k", api_shared_secret="s", data_dir=tmp_path,
        clerk_issuer="https://clerk.example.test", clerk_secret_key="sk_test_SECRET",
    )
    deps = AppDeps(store=store, graph="graph", seed_dir=None)
    app = create_app(settings, deps)
    async with app.router.lifespan_context(app):
        directory = deps.directory
        assert isinstance(directory, ClerkDirectory)
        http = directory._http
        assert not http.is_closed
    assert http.is_closed and deps.directory is None  # the next start builds a fresh one



async def test_profile_lookup_failure_is_503_not_sign_in(make_env):
    class DownDirectory:
        async def fetch(self, user_id):
            raise AuthError("Clerk lookup failed: ConnectError")

    env = make_env()
    env.deps.directory = DownDirectory()
    r = await env.client.get("/api/worlds")
    assert r.status_code == 503 and r.json() == {"detail": "account service unavailable"}
    assert env.deps.users.get(USER_A) is None
