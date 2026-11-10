from sagaloom.config import Settings
from sagaloom.llm import install_warning_filters, make_chat_model, make_embeddings


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
    async with client:
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
    async with client:
        model = make_gemini_model(_gemini_settings(), http_async_client=client)
        with pytest.raises(openai.APIStatusError) as info:
            await model.ainvoke("hi")
    assert gemini_error_event(info.value) is None


def test_llm_does_not_import_studio():
    import inspect

    import sagaloom.llm as llm

    imports = [l for l in inspect.getsource(llm).splitlines() if l.startswith(("import ", "from "))]
    assert not any("sagaloom.studio" in l for l in imports)


def _dump_with_field(field_name: str):
    """Dumps a ParsedChatCompletion whose `parsed` model the schema does not describe, the shape
    langchain-openai produces for structured output; returns the warnings recorded."""
    import warnings

    from openai.types.chat.parsed_chat_completion import (
        ParsedChatCompletion,
        ParsedChatCompletionMessage,
        ParsedChoice,
    )
    from pydantic import BaseModel

    class Out(BaseModel):
        a: int

    msg = ParsedChatCompletionMessage[None].model_construct(
        role="assistant", content="{}", parsed=Out(a=1)
    )
    choice = ParsedChoice[None].model_construct(index=0, finish_reason="stop", message=msg)
    done = ParsedChatCompletion[None].model_construct(
        id="x", created=1, model="m", object="chat.completion", choices=[choice]
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        install_warning_filters()
        if field_name == "parsed":
            done.model_dump()
        else:
            class Other(BaseModel):
                note: None = None

            Other.model_construct(note=Out(a=1)).model_dump()
    return caught


def test_parsed_serializer_warning_is_filtered():
    assert _dump_with_field("parsed") == []


def test_other_serializer_warnings_still_show():
    caught = _dump_with_field("note")
    assert len(caught) == 1 and "field_name='note'" in str(caught[0].message)


# ---------- OpenRouter in-band errors: a 200 whose body is an error, not a completion ----------

import json

from pydantic import BaseModel

from sagaloom.llm import OpenRouterChat
from sagaloom.structured import TRANSIENT_API_ERRORS, ask_structured

IN_BAND_ERROR = {
    "error": {
        "message": "Sorry, something went wrong.",
        "code": 502,
        "metadata": {"error_type": "provider_unavailable"},
    },
    "choices": None,
}


class Pick(BaseModel):
    n: int


def _completion(content: str) -> dict:
    return {
        "id": "c", "object": "chat.completion", "created": 0, "model": "m",
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _sse(*events: dict) -> httpx.Response:
    body = "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body.encode())


def _streamed(content: str) -> httpx.Response:
    base = {"id": "c", "object": "chat.completion.chunk", "created": 0, "model": "m"}
    return _sse(
        {**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": content}}]},
        {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
    )


def _openrouter(*replies: httpx.Response, streaming: bool = False):
    """An OpenRouterChat over a mock transport that answers with `replies` in order; also returns
    the list of requests it saw. No SDK retries, so one ainvoke is one request."""
    seen: list[httpx.Request] = []
    queue = list(replies)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    model = OpenRouterChat(
        model="m", api_key="k", base_url="https://openrouter.ai/api/v1",
        max_retries=0, streaming=streaming, http_async_client=client,
    )
    return model, client, seen


def _error_json() -> httpx.Response:
    return httpx.Response(200, json=IN_BAND_ERROR)


def _assert_provider_error(exc: BaseException) -> None:
    assert isinstance(exc, openai.InternalServerError)
    assert isinstance(exc, TRANSIENT_API_ERRORS)
    assert exc.status_code == 502
    assert "Sorry, something went wrong." in str(exc)
    assert "provider_unavailable" in str(exc)


async def test_in_band_error_on_a_structured_call_is_retried_as_transient():
    model, client, seen = _openrouter(_error_json(), httpx.Response(200, json=_completion('{"n": 7}')))
    async with client:
        out = await ask_structured(model, Pick, ["hi"], what="Test", retry_transient=True)
    assert out == Pick(n=7)
    assert len(seen) == 2


async def test_in_band_error_without_transient_retry_propagates_for_fail_closed():
    model, client, seen = _openrouter(_error_json(), _error_json())
    async with client:
        with pytest.raises(openai.InternalServerError) as info:
            await ask_structured(model, Pick, ["hi"], what="Judge", retry_transient=False)
    _assert_provider_error(info.value)
    assert len(seen) == 1


async def test_in_band_error_on_a_plain_call_is_an_internal_server_error():
    model, client, _ = _openrouter(_error_json())
    async with client:
        with pytest.raises(openai.InternalServerError) as info:
            await model.ainvoke("hi")
    _assert_provider_error(info.value)


async def test_in_band_error_on_a_streamed_structured_call_is_retried_as_transient():
    install_warning_filters()  # the app's filter for the streamed `parsed` serializer warning
    model, client, seen = _openrouter(_sse(IN_BAND_ERROR), _streamed('{"n": 3}'), streaming=True)
    async with client:
        out = await ask_structured(model, Pick, ["hi"], what="Test", retry_transient=True)
    assert out == Pick(n=3)
    assert len(seen) == 2


async def test_in_band_error_on_a_streamed_plain_call_is_an_internal_server_error():
    model, client, _ = _openrouter(_sse(IN_BAND_ERROR), streaming=True)
    async with client:
        with pytest.raises(openai.InternalServerError) as info:
            await model.ainvoke("hi")
    _assert_provider_error(info.value)


async def test_valid_replies_pass_through_untouched():
    model, client, _ = _openrouter(httpx.Response(200, json=_completion("hello")))
    async with client:
        assert (await model.ainvoke("hi")).content == "hello"
    model, client, _ = _openrouter(_streamed("hello"), streaming=True)
    async with client:
        assert (await model.ainvoke("hi")).content == "hello"


async def test_an_unparseable_structured_reply_is_still_an_invalid_reply():
    """Only an error body is translated: a reply that is not the schema stays an invalid reply."""
    from sagaloom.structured import INVALID_REPLY, InvalidReply

    model, client, seen = _openrouter(
        httpx.Response(200, json=_completion("not json")), httpx.Response(200, json=_completion("{}"))
    )
    async with client:
        with pytest.raises(InvalidReply) as info:
            await ask_structured(model, Pick, ["hi"], what="Test", retry_transient=False)
    assert isinstance(info.value.__cause__, INVALID_REPLY)
    assert len(seen) == 2


async def test_in_band_error_surfaces_as_model_unavailable():
    from sagaloom.web.sse import MODEL_UNAVAILABLE, _error_event

    model, client, _ = _openrouter(_error_json())
    async with client:
        with pytest.raises(openai.InternalServerError) as info:
            await model.ainvoke("hi")
    assert gemini_error_event(info.value) is None
    assert _error_event(info.value)["data"] == {"message": MODEL_UNAVAILABLE, "retryable": True}


def _error_body(code) -> dict:
    return {**IN_BAND_ERROR, "error": {**IN_BAND_ERROR["error"], "code": code}}


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("structured", [False, True])
async def test_an_in_band_client_error_is_left_as_it_was(streaming, structured):
    """An explicit 4xx inside a 200 is not a fake 502: retrying a client error cannot help."""
    body = _error_body(400)
    reply = _sse(body) if streaming else httpx.Response(200, json=body)
    model, client, _ = _openrouter(reply, streaming=streaming)
    runnable = model.with_structured_output(Pick) if structured else model
    async with client:
        with pytest.raises(Exception) as info:
            await runnable.ainvoke("hi")
    exc = info.value
    assert not isinstance(exc, TRANSIENT_API_ERRORS)
    # Each path surfaces its own untranslated error: a bare `openai.APIError` from the stream,
    # langchain's `TypeError` on a structured reply, and its `ValueError` on a plain one.
    expected = openai.APIError if streaming else TypeError if structured else ValueError
    assert type(exc) is expected


@pytest.mark.parametrize("code", [None, "server_error", 408, 429, 500, 503])
@pytest.mark.parametrize("streaming", [False, True])
async def test_in_band_errors_that_may_pass_are_translated(code, streaming):
    body = _error_body(code)
    if code is None:
        del body["error"]["code"]
    reply = _sse(body) if streaming else httpx.Response(200, json=body)
    model, client, _ = _openrouter(reply, streaming=streaming)
    async with client:
        with pytest.raises(openai.InternalServerError) as info:
            await model.ainvoke("hi")
    assert "in-band provider error" in str(info.value)
    assert info.value.request.url == httpx.URL("https://openrouter.ai/api/v1/chat/completions")


async def test_a_genuine_agenerate_error_with_a_valid_body_passes_through(monkeypatch):
    from langchain_openai import ChatOpenAI

    boom = RuntimeError("boom")
    boom.response = httpx.Response(
        200, json=_completion("x"), request=httpx.Request("POST", "https://x/chat/completions")
    )

    async def fail(self, *a, **k):
        raise boom

    monkeypatch.setattr(ChatOpenAI, "_agenerate", fail)
    model, client, _ = _openrouter()
    async with client:
        with pytest.raises(RuntimeError) as info:
            await model.ainvoke("hi")
    assert info.value is boom


async def test_a_status_error_inside_astream_passes_through(monkeypatch):
    from langchain_openai import ChatOpenAI

    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    real = openai.RateLimitError("slow down", response=httpx.Response(429, request=req), body={"x": 1})

    async def fail(self, *a, **k):
        raise real
        yield  # pragma: no cover

    monkeypatch.setattr(ChatOpenAI, "_astream", fail)
    model, client, _ = _openrouter(streaming=True)
    async with client:
        with pytest.raises(openai.RateLimitError) as info:
            await model.ainvoke("hi")
    assert info.value is real
