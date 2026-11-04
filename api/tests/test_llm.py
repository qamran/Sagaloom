from sagaloom.config import Settings
from sagaloom.llm import make_chat_model, make_embeddings


def _settings(**kw):
    return Settings(_env_file=None, openrouter_api_key="test-key", api_shared_secret="s",
                    web_origin="http://localhost:3000", **kw)


def test_chat_model_pins_provider_and_disables_fallbacks():
    s = _settings()
    m = make_chat_model(s)
    assert m.extra_body == {
        "provider": {"order": s.provider_order, "allow_fallbacks": False},
        "usage": {"include": True},
    }
    assert m.openai_api_base == s.openrouter_base_url
    assert m.model_name == s.chat_model
    assert m.stream_usage is True
    assert m.request_timeout == 60
    assert m.temperature == 0.0


def test_chat_model_override_model_and_temperature():
    m = make_chat_model(_settings(), model="x/y", temperature=0.7)
    assert m.model_name == "x/y"
    assert m.temperature == 0.7


def test_chat_model_retries_three_times():
    assert make_chat_model(_settings()).max_retries == 3


def test_embeddings_config():
    s = _settings()
    e = make_embeddings(s)
    assert e.model == s.embed_model
    assert e.openai_api_base == s.openrouter_base_url
    assert e.check_embedding_ctx_length is False
