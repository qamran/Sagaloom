"""Studio data: the feature map (R20.5), providers (R20.7, R11.G9) and model settings (R11.G10)."""

import json

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
        "agent_purpose", "agentic_rag", "human_in_the_loop", "memory", "token_cost",
        "langsmith", "multi_provider", "security_guard", "external_tools",
    ]
    assert all(c.req_ids and c.title and c.brief_ref and c.detail for c in cards)
    live = {c.id for c in cards if c.status == "live"}
    assert live == {"agent_purpose", "agentic_rag", "human_in_the_loop", "memory", "token_cost", "security_guard"}
    assert card(cards, "external_tools").status == "off"
    assert card(cards, "external_tools").try_href is None
    assert card(cards, "agentic_rag").try_href.startswith("/chat?prompt=")


def test_feature_map_multi_provider_follows_gemini_key(tmp_path):
    assert card(build_feature_map(make_settings(tmp_path), AppDeps()), "multi_provider").status == "off"
    s = make_settings(tmp_path, gemini_api_key=GEMINI_KEY)
    assert card(build_feature_map(s, AppDeps()), "multi_provider").status == "configured"


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
    assert card(build_feature_map(s, AppDeps()), "multi_provider").status == "off"
    assert providers_status(s)[1].key_set is False
    s2 = make_settings(tmp_path, gemini_api_key=GEMINI_KEY)
    assert card(build_feature_map(s2, AppDeps()), "multi_provider").status == "configured"
    assert providers_status(s2)[1].key_set is True


def test_model_for_tags_the_role_on_the_model(tmp_path):
    from sagaloom.web.app import make_model_for

    s = make_settings(tmp_path)
    model_for = make_model_for(s, ModelSettings(tmp_path / "ms.json", s))
    assert model_for("judge").metadata["role"] == "judge"
    assert model_for("extractor").metadata["role"] == "extractor"
