"""Studio and model switching over HTTP (R11.G10, R20.1, R20.7)."""

import itertools
from urllib.parse import parse_qs, urlsplit

from fakes import (
    KEY, SECRET, TOKEN_A, USER_A, W, Env, FakeDirectory, FakeJudge, FakeVerifier, ScriptedChat, StubLLM,
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
from sagaloom.web.app import AppDeps, create_app, make_model_for


class NamedJudge(FakeJudge):
    model_name: str = ""

    @property
    def _identifying_params(self):
        return {"model_name": self.model_name}


def build_switchable_env(store, tmp_path, aclose_later) -> Env:
    settings = Settings(_env_file=None, openrouter_api_key=KEY, api_shared_secret=SECRET, data_dir=tmp_path)
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
    env = make_env()
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
    assert len(body["features"]) == 13
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
    env = make_env()
    r = await env.client.put(
        "/api/settings/models", json={"role": "agent", "model": "gemini-3.5-flash-lite"}
    )
    assert r.status_code == 422
    import inspect

    import sagaloom.web.app as app_mod

    assert "make_gemini_model" not in inspect.getsource(app_mod)
