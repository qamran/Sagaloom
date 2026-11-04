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


def _chunks(cost=0.0123):
    base = {"id": "x", "model": "m", "object": "chat.completion.chunk"}
    return [
        {**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": "Hel"}}]},
        {**base, "choices": [{"index": 0, "delta": {"content": "lo"}, "finish_reason": "stop"}]},
        {**base, "choices": [], "usage": {"prompt_tokens": 1000, "completion_tokens": 500,
                                          "total_tokens": 1500, "cost": cost}},
    ]


def test_streamed_chunks_keep_openrouter_cost():
    from langchain_core.messages import AIMessageChunk

    from sagaloom.usage import extract_usage

    s = _settings()
    m = make_chat_model(s)
    merged = None
    for raw in _chunks():
        gen = m._convert_chunk_to_generation_chunk(raw, AIMessageChunk, None)
        if gen is not None:
            merged = gen.message if merged is None else merged + gen.message
    assert merged.content == "Hello"
    u = extract_usage(merged, s)
    assert (u.prompt_tokens, u.completion_tokens) == (1000, 500)
    assert u.cost_usd == 0.0123  # not the estimate


def test_non_streamed_result_keeps_cost():
    from langchain_core.messages import AIMessage

    from sagaloom.usage import extract_usage

    s = _settings()
    msg = AIMessage(content="x", response_metadata={"token_usage": {
        "prompt_tokens": 10, "completion_tokens": 5, "cost": 0.5}})
    assert extract_usage(msg, s).cost_usd == 0.5


def test_chat_model_provider_param_pins_that_provider_without_fallbacks():
    m = make_chat_model(_settings(), model="anthropic/claude-sonnet-5.5", provider="anthropic")
    assert m.extra_body["provider"] == {"order": ["anthropic"], "allow_fallbacks": False}
