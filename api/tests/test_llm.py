from sagaloom.config import Settings
from sagaloom.llm import make_chat_model, make_embeddings


def _settings(**kw):
    # gemini_api_key=None by default: init kwargs outrank a GEMINI_API_KEY exported in the shell.
    kw.setdefault("gemini_api_key", None)
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


# ---------- Gemini: configured-only; every test uses a fake key and a MockTransport ----------

import httpx
import openai
import pytest

from sagaloom.llm import GEMINI_BASE_URL, make_gemini_model
from sagaloom.web.sse import gemini_error_event


def _gemini_settings(**kw):
    return _settings(gemini_api_key="test", **kw)


def _mock_client(status: int):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json={"error": {"message": "nope"}})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), seen


def test_gemini_model_config():
    m = make_gemini_model(_gemini_settings())
    assert GEMINI_BASE_URL == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert m.openai_api_base == GEMINI_BASE_URL
    assert m.model_name == "gemini-3.5-flash-lite"
    assert m.max_retries == 0
    assert not m.extra_body


def test_gemini_model_needs_a_key():
    with pytest.raises(ValueError, match="GEMINI_API_KEY is not set"):
        make_gemini_model(_settings())


@pytest.mark.parametrize(
    "status,copy",
    [
        (429, "Gemini's free tier is out of requests right now."),
        (503, "Gemini is overloaded right now."),
    ],
)
async def test_gemini_errors_once(status, copy):
    client, seen = _mock_client(status)
    model = make_gemini_model(_gemini_settings(), http_async_client=client)
    with pytest.raises(openai.APIStatusError) as info:
        await model.ainvoke("hi")
    assert len(seen) == 1
    assert seen[0].url.host == "generativelanguage.googleapis.com"
    assert gemini_error_event(info.value) == {
        "message": copy,
        "retryable": False,
        "switch_back": "openrouter",
        "switch_back_label": "Switch back to OpenRouter",
    }


async def test_gemini_other_status_is_not_special():
    client, _ = _mock_client(500)
    model = make_gemini_model(_gemini_settings(), http_async_client=client)
    with pytest.raises(openai.APIStatusError) as info:
        await model.ainvoke("hi")
    assert gemini_error_event(info.value) is None


def test_llm_does_not_import_studio():
    import inspect

    import sagaloom.llm as llm

    imports = [l for l in inspect.getsource(llm).splitlines() if l.startswith(("import ", "from "))]
    assert not any("sagaloom.studio" in l for l in imports)
