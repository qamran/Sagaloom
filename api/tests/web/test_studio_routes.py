"""Studio and model switching over HTTP (R11.G10, R20.1, R20.7)."""

import itertools
from urllib.parse import parse_qs, urlsplit

from fakes import (
    ADMIN_A, KEY, SECRET, TOKEN_A, TOKEN_B, USER_A, USER_B, W, Env, FakeDirectory, FakeJudge, FakeVerifier, ScriptedChat, StubLLM,
    create_call, signed_in_client,
)

from checkpointers import memory_checkpointer
from sagaloom.config import Settings
from sagaloom.graph.build import build_graph
from sagaloom.router import RouteDecision
from sagaloom.guard import GuardVerdict
from sagaloom.model_settings import ModelSettings
from sagaloom.models import Entry
from sagaloom.promptlog import PromptLog
from sagaloom.store.threads import ThreadRegistry
from sagaloom.store.worlds import WorldRegistry
from sagaloom.web.access import ADMIN_ONLY
from sagaloom.web.app import AppDeps, create_app, make_model_for


class NamedJudge(FakeJudge):
    model_name: str = ""

    @property
    def _identifying_params(self):
        return {"model_name": self.model_name}


def build_switchable_env(store, tmp_path, aclose_later) -> Env:
    settings = Settings(
        _env_file=None, openrouter_api_key=KEY, api_shared_secret=SECRET, data_dir=tmp_path,
        admin_email=ADMIN_A,  # the model switches below are admin-only
    )
    ms = ModelSettings(tmp_path / "model_settings.json", settings)
    agent = ScriptedChat(script=itertools.cycle([create_call(title="Velmar Docks", content="Drafting.")]))
    built: list[tuple[str, str]] = []

    def factory(role, model):
        built.append((role, model))
        if role == "guard":
            return StubLLM(GuardVerdict(verdict="safe", reason="ok"))
        if role == "router":
            return StubLLM(RouteDecision(mode="edit"))
        return NamedJudge(model_name=model) if role == "judge" else agent

    graph = build_graph(
        store=store,
        model_for=make_model_for(settings, ms, factory),
        checkpointer=memory_checkpointer(),
    )
    worlds = WorldRegistry(tmp_path / "worlds.json")
    worlds.create("World One", world_id=W, owner_id=USER_A)
    deps = AppDeps(
        store=store,
        worlds=worlds,
        threads=ThreadRegistry(tmp_path / "threads.sqlite"),
        graph=graph,
        settings=settings,
        promptlog=PromptLog(tmp_path / "prompts.sqlite"),
        model_settings=ms,
        verifier=FakeVerifier({TOKEN_A: USER_A}),
        directory=FakeDirectory(),
        seed_dir=None,  # no per-account Velmar copy: tests use world `W`
    )
    app = create_app(settings, deps)
    env = Env(signed_in_client(app, TOKEN_A, aclose_later), app, deps, agent, settings, aclose_later)
    env.built = built  # type: ignore[attr-defined]
    return env


async def test_set_model_rejects_model_not_on_allowlist_with_422(make_env):
    env = make_env(admin=True)
    r = await env.client.put("/api/settings/models", json={"role": "judge", "model": "evil/not-allowed"})
    assert r.status_code == 422
    r = await env.client.put("/api/settings/models", json={"role": "nobody", "model": "openai/gpt-6-luna"})
    assert r.status_code == 422
    got = (await env.client.get("/api/settings/models")).json()
    assert got["mapping"]["judge"] == "openai/gpt-6-luna"
    ids = {m["id"] for m in got["allowed"]}
    assert len(ids) == 36 and "evil/not-allowed" not in ids

    ok = await env.client.put(
        "/api/settings/models", json={"role": "judge", "model": "anthropic/claude-sonnet-5.5"}
    )
    assert ok.status_code == 200 and ok.json()["mapping"]["judge"] == "anthropic/claude-sonnet-5.5"


async def test_settings_models_need_the_secret(make_env):
    env = make_env()
    env.client.headers.pop("X-Sagaloom-Secret")
    assert (await env.client.get("/api/settings/models")).status_code == 401
    r = await env.client.put("/api/settings/models", json={"role": "judge", "model": "openai/gpt-6-luna"})
    assert r.status_code == 401


async def test_switching_judge_model_shows_in_next_prompt_record(store, tmp_path, aclose_later):
    store.upsert_entry(Entry(id="ent_0001", world_id=W, title="Velmar", type="place", body="A city."))
    env = build_switchable_env(store, tmp_path, aclose_later)

    tid1 = await env.new_thread()
    await env.send(tid1, "Add the Velmar docks")
    first = (await env.client.get(f"/api/threads/{tid1}/llm-log")).json()
    assert len(first) == 2 and first[-1]["model"] == "openai/gpt-6-luna"
    assert first[-1]["role"] == "judge"

    r = await env.client.put("/api/settings/models", json={"role": "judge", "model": "openai/gpt-6.1-terra"})
    assert r.status_code == 200

    tid2 = await env.new_thread()
    await env.send(tid2, "Add the Velmar docks again")
    second = (await env.client.get(f"/api/threads/{tid2}/llm-log")).json()
    assert second[-1]["model"] == "openai/gpt-6.1-terra"
    assert ("judge", "openai/gpt-6.1-terra") in env.built


async def test_studio_returns_features_providers_mermaid_and_no_keys(make_env):
    env = make_env()
    env.deps.settings = Settings(
        _env_file=None,
        openrouter_api_key=KEY,
        api_shared_secret=SECRET,
        gemini_api_key="AIza-GEMINI-SECRET-123",
        data_dir=env.settings.data_dir,
    )
    r = await env.client.get("/api/studio")
    body = r.json()
    assert len(body["features"]) == 14
    assert [p["name"] for p in body["providers"]] == ["OpenRouter", "Gemini"]
    assert body["providers"][1]["key_set"] is True
    assert "agent" in body["mermaid"] and "graph" in body["mermaid"]
    assert set(body["usage"]) >= {"prompt_tokens", "completion_tokens", "cost_usd"}
    assert isinstance(body["usage"]["by_model"], list)
    for secret in ("AIza-GEMINI-SECRET-123", KEY, SECRET):
        assert secret not in r.text


async def test_reference_try_it_states_a_fact(make_env):
    env = make_env()
    body = (await env.client.get("/api/studio")).json()
    card = next(f for f in body["features"] if f["id"] == "external_tools")
    prompt = parse_qs(urlsplit(card["try_href"]).query)["prompt"][0]
    assert "customs house" in prompt


async def test_gemini_never_in_model_for(make_env):
    env = make_env(admin=True)
    r = await env.client.put(
        "/api/settings/models", json={"role": "agent", "model": "gemini-3.5-flash-lite"}
    )
    assert r.status_code == 422
    import inspect

    import sagaloom.web.app as app_mod

    assert "make_gemini_model" not in inspect.getsource(app_mod)


# ---- M5: per-user usage, the admin's "All users", the accounts card (spec §5.2, §5.5) ----


def _cost_rec(id: str, thread_id: str, cost: float):
    from sagaloom.promptlog import PromptRecord

    return PromptRecord(
        id=id, thread_id=thread_id, run_id="r", provider="openrouter", model="openai/gpt-6-luna",
        role="agent", request={"messages": [], "tools": []},
        response={"prompt_tokens": 7, "completion_tokens": 3, "cost_usd": cost},
        started_at="2026-01-01T00:00:01+00:00",
    )


async def test_studio_usage_is_mine(make_env):
    env = make_env([create_call()])
    tid = await env.new_thread()
    r, _ = await env.send(tid)
    assert r.status_code == 200
    log = env.deps.promptlog
    mine = log.usage(user_id=USER_A)
    assert mine.prompt_tokens > 0  # the turn's records were written with A's id (the world's owner)
    assert log.usage(thread_id=tid) == mine
    log.add(_cost_rec("b-call", "tb", 0.5), user_id=USER_B)
    log.add(_cost_rec("nobody", "gone", 0.25))

    body = (await env.client.get("/api/studio")).json()
    assert body["usage"]["prompt_tokens"] == mine.prompt_tokens
    assert body["usage"]["cost_usd"] == mine.cost_usd
    assert sum(m["calls"] for m in body["usage"]["by_model"]) == len(log.list(tid))
    token_card = next(f for f in body["features"] if f["id"] == "token_cost")
    assert f"${mine.cost_usd:.4f}" in token_card["detail"]

    b = (await env.as_user(TOKEN_B).get("/api/studio?scope=mine")).json()
    assert (b["usage"]["prompt_tokens"], b["usage"]["cost_usd"]) == (7, 0.5)
    assert [m["calls"] for m in b["usage"]["by_model"]] == [1]
    assert "$0.5000" in next(f for f in b["features"] if f["id"] == "token_cost")["detail"]


async def test_studio_scope_all_admin_only(make_env):
    env = make_env(admin=True)
    log = env.deps.promptlog
    log.add(_cost_rec("a-call", "ta", 0.125), user_id=USER_A)
    log.add(_cost_rec("b-call", "tb", 0.5), user_id=USER_B)
    log.add(_cost_rec("nobody", "gone", 0.25))
    all_users = (await env.client.get("/api/studio?scope=all")).json()["usage"]
    assert (all_users["prompt_tokens"], all_users["cost_usd"]) == (21, 0.875)
    assert [m["calls"] for m in all_users["by_model"]] == [3]
    mine = (await env.client.get("/api/studio")).json()["usage"]
    assert (mine["prompt_tokens"], mine["cost_usd"]) == (7, 0.125)
    r = await env.as_user(TOKEN_B).get("/api/studio?scope=all")
    assert r.status_code == 403 and r.json() == {"detail": ADMIN_ONLY}
    assert (await env.client.get("/api/studio?scope=everyone")).status_code == 422


async def test_feature_map_has_accounts_card(make_env):
    env = make_env()
    env.deps.settings.clerk_issuer = None
    card = next(f for f in (await env.client.get("/api/studio")).json()["features"] if f["id"] == "accounts")
    assert card["status"] == "off"
    env.deps.settings.clerk_issuer = "https://clerk.example.test"
    card = next(f for f in (await env.client.get("/api/studio")).json()["features"] if f["id"] == "accounts")
    assert (card["title"], card["status"], card["try_href"]) == ("User accounts", "live", "/canon")
    assert card["detail"] == "Sign-in by Clerk; every author sees only their own worlds."
    assert card["brief_ref"] == "Medium 4"


async def test_memory_card_counts_my_threads(make_env):
    env = make_env(admin=True)
    env.deps.worlds.create("B's World", world_id="wb", owner_id=USER_B)
    for world_id in (W, "wb", "wb"):
        env.deps.threads.create(world_id)
    env.deps.threads.create("gone")  # a thread whose world is gone: nobody's

    def memory_detail(body):
        return next(f for f in body["features"] if f["id"] == "memory")["detail"]

    assert ", 1 threads." in memory_detail((await env.client.get("/api/studio")).json())
    assert ", 2 threads." in memory_detail((await env.as_user(TOKEN_B).get("/api/studio")).json())
    assert ", 4 threads." in memory_detail((await env.client.get("/api/studio?scope=all")).json())


async def test_studio_world_filter_shows_only_that_world(make_env):
    """`world_id` narrows usage, the cost line and the thread count to the selected world."""
    env = make_env(admin=True)
    env.deps.worlds.create("Second", world_id="w2", owner_id=USER_A)
    env.deps.worlds.create("B's World", world_id="wb", owner_id=USER_B)
    t1 = env.deps.threads.create(W)
    t2 = env.deps.threads.create("w2")
    env.deps.threads.create("w2")
    log = env.deps.promptlog
    log.add(_cost_rec("c1", t1, 0.125), user_id=USER_A)
    log.add(_cost_rec("c2", t2, 0.5), user_id=USER_A)

    def card(body, id):
        return next(f for f in body["features"] if f["id"] == id)["detail"]

    one = (await env.client.get(f"/api/studio?world_id={W}")).json()
    assert (one["usage"]["prompt_tokens"], one["usage"]["cost_usd"]) == (7, 0.125)
    assert [m["calls"] for m in one["usage"]["by_model"]] == [1]
    assert "$0.1250" in card(one, "token_cost")
    assert ", 1 threads." in card(one, "memory")

    two = (await env.client.get("/api/studio?world_id=w2")).json()
    assert two["usage"]["cost_usd"] == 0.5
    assert ", 2 threads." in card(two, "memory")

    # No world: every world of the account, as before.
    assert (await env.client.get("/api/studio")).json()["usage"]["cost_usd"] == 0.625
    # A world with no calls yet: zero, not everything.
    env.deps.worlds.create("Empty", world_id="w3", owner_id=USER_A)
    empty = (await env.client.get("/api/studio?world_id=w3")).json()
    assert (empty["usage"]["cost_usd"], empty["usage"]["by_model"]) == (0.0, [])
    # Someone else's world: 404, as everywhere else.
    assert (await env.client.get("/api/studio?world_id=wb")).status_code == 404
    # The admin's "All users" view stays app-wide and ignores the world.
    assert (await env.client.get(f"/api/studio?scope=all&world_id={W}")).json()["usage"]["cost_usd"] == 0.625
