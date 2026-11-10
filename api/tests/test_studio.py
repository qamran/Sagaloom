"""Studio data: the feature map (R20.5), providers (R20.7, R11.G9) and model settings (R11.G10)."""

import json
from urllib.parse import parse_qs, quote, urlsplit

import pytest

from sagaloom.config import Settings
from sagaloom.model_settings import ModelSettings
from sagaloom.studio import build_feature_map, providers_status
from sagaloom.web.app import AppDeps

GEMINI_KEY = "AIza-GEMINI-SECRET-123"
OR_KEY = "sk-or-SECRET-456"


def make_settings(tmp_path, **kw) -> Settings:
    return Settings(
        _env_file=None,
        openrouter_api_key=kw.pop("openrouter_api_key", OR_KEY),
        api_shared_secret="shared-secret-789",
        data_dir=tmp_path,
        **kw,
    )


def card(cards, id):
    return next(c for c in cards if c.id == id)


def test_feature_map_langsmith_live_only_when_env_set(tmp_path, monkeypatch):
    s = make_settings(tmp_path)
    for var in ("LANGSMITH_TRACING", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert card(build_feature_map(s, AppDeps()), "langsmith").status == "off"

    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    assert card(build_feature_map(s, AppDeps()), "langsmith").status == "off"  # no key yet

    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2-SECRET-000")
    cards = build_feature_map(s, AppDeps())
    assert card(cards, "langsmith").status == "live"
    assert "lsv2-SECRET-000" not in json.dumps([c.model_dump() for c in cards])

    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    assert card(build_feature_map(s, AppDeps()), "langsmith").status == "off"


def test_feature_map_lists_all_brief_bonus_cards_with_req_ids(tmp_path, monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    cards = build_feature_map(make_settings(tmp_path), AppDeps())
    assert [c.id for c in cards] == [
        "agent_purpose", "agentic_rag", "human_in_the_loop", "router", "memory", "token_cost",
        "langsmith", "multi_provider", "security_guard", "tools", "external_tools",
        "injection_safe_extraction",
    ]
    assert all(c.req_ids and c.title and c.brief_ref and c.detail for c in cards)
    live = {c.id for c in cards if c.status == "live"}
    assert live == {
        "agent_purpose", "agentic_rag", "human_in_the_loop", "router", "memory", "token_cost",
        "security_guard", "tools", "external_tools", "multi_provider", "injection_safe_extraction",
    }
    router = card(cards, "router")
    assert (router.brief_ref, router.req_ids, router.status) == ("Sprint topic", ["R6.5"], "live")
    assert router.try_href == "/chat?prompt=Give%20me%20three%20ideas%20for%20a%20festival%20in%20Velmar."
    assert card(cards, "tools").brief_ref == "Medium 6"
    assert card(cards, "tools").req_ids == ["R11.G1", "R11.G3"]
    assert card(cards, "external_tools").status == "live"
    assert card(cards, "external_tools").detail == (
        "Wikipedia reference tool; fan-wiki import arrives in Wave 6."
    )
    assert card(cards, "external_tools").try_href.startswith("/chat?prompt=")
    assert card(cards, "agentic_rag").try_href.startswith("/chat?prompt=")


def test_try_it_links_are_url_encoded(tmp_path):
    cards = build_feature_map(make_settings(tmp_path), AppDeps())
    prompts = [c for c in cards if c.try_href and c.try_href.startswith("/chat?prompt=")]
    assert len(prompts) >= 4
    for c in prompts:
        assert " " not in c.try_href and "," not in c.try_href
        decoded = parse_qs(urlsplit(c.try_href).query)["prompt"][0]
        assert c.try_href == "/chat?prompt=" + quote(decoded)
    ext = card(cards, "external_tools").try_href
    assert "%27" in ext and "'" not in ext
    assert parse_qs(urlsplit(ext).query)["prompt"][0] == (
        "What did Byzantine trade routes look like? I want Velmar's harbour to feel like that. "
        "Lantern Quay's harbour runs a customs house, like Byzantine ports."
    )
    hitl = card(cards, "human_in_the_loop")
    assert parse_qs(urlsplit(hitl.try_href).query)["prompt"][0] == (
        "Add a place called Ostra, a port town with a deep harbour."
    )


def test_studio_lists_injection_safe_extraction_card(tmp_path):
    c = card(build_feature_map(make_settings(tmp_path), AppDeps()), "injection_safe_extraction")
    assert c.title == "Injection-safe extraction"
    assert c.req_ids == ["R13.6", "R13.7", "R3.5"]
    assert c.status == "live" and c.try_href == "/import"
    for words in ("structured output", "no tools", "untrusted data", "verbatim", "approval"):
        assert words in c.detail


def test_feature_map_multi_provider_follows_gemini_key(tmp_path):
    off = card(build_feature_map(make_settings(tmp_path), AppDeps()), "multi_provider")
    assert off.status == "live" and off.brief_ref == "Medium 7"
    assert off.detail == (
        "Per-role model switching across OpenRouter vendors. Gemini direct is not configured."
    )
    s = make_settings(tmp_path, gemini_api_key=GEMINI_KEY)
    on = card(build_feature_map(s, AppDeps()), "multi_provider")
    assert on.status == "live"
    assert on.detail == (
        "Per-role model switching across OpenRouter vendors. Gemini direct is configured for show only: "
        "never selectable, never called."
    )


def test_providers_status_never_contains_key_values_and_marks_gemini_demo_only(tmp_path):
    s = make_settings(tmp_path, gemini_api_key=GEMINI_KEY)
    providers = providers_status(s)
    dumped = json.dumps([p.model_dump() for p in providers])
    for secret in (GEMINI_KEY, OR_KEY, "shared-secret-789"):
        assert secret not in dumped
    openrouter, gemini = providers
    assert openrouter.name == "OpenRouter" and openrouter.key_set
    assert {m.role for m in openrouter.models} == {"agent", "judge", "extractor", "embeddings"}
    assert gemini.name == "Gemini" and gemini.key_set
    assert "demo only, not used for real calls" in gemini.role
    assert "free-tier" in gemini.notice.lower() and "Google" in gemini.notice

    none = providers_status(make_settings(tmp_path))[1]
    assert none.key_set is False


def test_model_settings_default_persist_and_reject(tmp_path):
    s = make_settings(tmp_path)
    ms = ModelSettings(tmp_path / "model_settings.json", s)
    assert ms.get_model_settings() == {r: "openai/gpt-6-luna" for r in ("agent", "judge", "extractor", "guard")}
    ms.set_model("judge", "anthropic/claude-sonnet-5.5")
    assert ModelSettings(tmp_path / "model_settings.json", s).get_model_settings()["judge"] == (
        "anthropic/claude-sonnet-5.5"
    )
    with pytest.raises(ValueError):
        ms.set_model("judge", "evil/not-allowed")
    with pytest.raises(ValueError):
        ms.set_model("nobody", "openai/gpt-6-luna")  # type: ignore[arg-type]
    assert ms.get_model_settings()["judge"] == "anthropic/claude-sonnet-5.5"


def test_allowlist_has_prices(tmp_path):
    allowed = make_settings(tmp_path).allowed_models
    assert len(allowed) == 36 and all(m.price_in >= 0 and m.price_out >= 0 for m in allowed)
    assert "openai/gpt-6-luna" in {m.id for m in allowed}


def test_make_model_for_pins_the_provider_of_the_selected_model(tmp_path):
    from sagaloom.web.app import make_model_for

    s = make_settings(tmp_path)
    ms = ModelSettings(tmp_path / "model_settings.json", s)
    model_for = make_model_for(s, ms)
    assert model_for("judge").extra_body["provider"]["order"] == ["openai"]  # Luna
    ms.set_model("judge", "anthropic/claude-sonnet-5.5")
    assert model_for("judge").extra_body["provider"] == {"order": ["anthropic"], "allow_fallbacks": False}
    ms.set_model("judge", "google/gemini-3.8-flash")
    assert model_for("judge").extra_body["provider"]["order"] == ["google-ai-studio"]
    assert model_for("agent").extra_body["provider"]["order"] == ["openai"]


def test_every_allowlisted_model_has_a_provider(tmp_path):
    assert all(m.provider for m in make_settings(tmp_path).allowed_models)


def test_gemini_key_set_is_consistent_and_false_for_an_empty_key(tmp_path):
    s = make_settings(tmp_path, gemini_api_key="")
    assert "not configured" in card(build_feature_map(s, AppDeps()), "multi_provider").detail
    assert providers_status(s)[1].key_set is False
    s2 = make_settings(tmp_path, gemini_api_key=GEMINI_KEY)
    assert "configured for show only" in card(build_feature_map(s2, AppDeps()), "multi_provider").detail
    assert providers_status(s2)[1].key_set is True


def test_model_for_tags_the_role_on_the_model(tmp_path):
    from sagaloom.web.app import make_model_for

    s = make_settings(tmp_path)
    model_for = make_model_for(s, ModelSettings(tmp_path / "ms.json", s))
    assert model_for("judge").metadata["role"] == "judge"
    assert model_for("extractor").metadata["role"] == "extractor"


def test_router_role_alias(tmp_path):
    """The router runs on the guard's model (spec 3.4) but is its own role on prompt records."""
    from sagaloom.model_settings import ROLES
    from sagaloom.web.app import make_model_for

    s = make_settings(tmp_path)
    ms = ModelSettings(tmp_path / "ms.json", s)
    built: list[tuple[str, str]] = []

    class Fake:
        def __init__(self, role, model):
            self.model_name, self.metadata = model, {}

    def factory(role, model):
        built.append((role, model))
        return Fake(role, model)

    model_for = make_model_for(s, ms, factory)
    router, guard = model_for("router"), model_for("guard")
    assert router.model_name == guard.model_name == ms.get_model_settings()["guard"]
    assert router.metadata["role"] == "router" and guard.metadata["role"] == "guard"
    assert router is not guard and model_for("router") is router
    ms.set_model("guard", "anthropic/claude-sonnet-5.5")
    assert model_for("router").model_name == "anthropic/claude-sonnet-5.5"
    assert built[-1] == ("router", "anthropic/claude-sonnet-5.5")
    assert "router" not in ROLES  # not switchable on its own


def test_env_default_model_off_the_allowlist_fails_fast(tmp_path):
    from sagaloom.model_settings import validate_role_models
    from sagaloom.web.app import create_app

    validate_role_models(make_settings(tmp_path))  # the built-in defaults are allowed
    bad = make_settings(tmp_path, judge_model="foo/bar")
    with pytest.raises(ValueError, match=r"allowed_models\.json: JUDGE_MODEL=foo/bar"):
        validate_role_models(bad)
    with pytest.raises(ValueError, match="JUDGE_MODEL=foo/bar"):
        create_app(bad)


async def test_default_app_reports_a_bad_env_model_at_startup(tmp_path, monkeypatch):
    import sagaloom.web.app as app_module

    # Never read the real .env files: replace the Settings() the default app builds.
    monkeypatch.setattr(app_module, "Settings", lambda: make_settings(tmp_path, chat_model="foo/bar"))
    app = app_module._build_default_app()
    with pytest.raises(RuntimeError, match="misconfigured: .*CHAT_MODEL=foo/bar"):
        async with app.router.lifespan_context(app):
            pass


def test_security_guard_card_follows_the_guard_setting(tmp_path):
    from sagaloom.settings_store import DevSettingsPatch, DevSettingsStore

    store = DevSettingsStore(tmp_path / "dev_settings.json")
    deps = AppDeps(dev_settings=store)
    on = card(build_feature_map(make_settings(tmp_path), deps), "security_guard")
    assert on.status == "live"
    assert {"R13.1", "R12.4"} <= set(on.req_ids)
    assert "input guard checks each message" in on.detail
    store.update(DevSettingsPatch(guard_enabled=False))
    assert card(build_feature_map(make_settings(tmp_path), deps), "security_guard").status == "off"
    # no store wired: falls back to on
    assert card(build_feature_map(make_settings(tmp_path), AppDeps()), "security_guard").status == "live"


def test_memory_card_describes_both_memories(tmp_path, monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    c = card(build_feature_map(make_settings(tmp_path), AppDeps()), "memory")
    assert c.req_ids == ["R10.1", "R10.2", "R18.6", "R18.7"]
    assert "LangGraph Store" in c.detail
    assert c.detail.startswith("Short-term: a SQLite checkpointer")
