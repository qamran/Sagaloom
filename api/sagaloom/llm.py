import warnings
from collections.abc import AsyncIterator
from typing import Any

import httpx
import openai
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from sagaloom.config import GEMINI_MODEL, Settings

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def install_warning_filters() -> None:
    """Hides one third-party warning: Pydantic's serializer warning for `parsed`.

    It comes from langchain-openai's streamed structured-output path, the one the graph uses:
    `beta.chat.completions.stream`, then `model_dump()` of the final parsed completion. There
    `parsed` holds our structured-output model while the completion type is parametrised with
    none of it, so Pydantic warns on every structured call. The value is the correct one, so only
    that exact message is ignored; any other serializer warning still shows."""
    warnings.filterwarnings(
        "ignore",
        message=r"Pydantic serializer warnings:\s+PydanticSerializationUnexpectedValue\([^\n]*field_name='parsed'",
        category=UserWarning,
    )


def _may_pass(err: dict) -> bool:
    """Whether an in-band error may pass on a retry: its `code` is absent, not an int (OpenRouter
    also sends strings such as "server_error"), 408, 429 or 5xx. An explicit other 4xx cannot."""
    code = err.get("code")
    return not isinstance(code, int) or isinstance(code, bool) or code in (408, 429) or code >= 500


def _in_band_error(body: Any) -> dict | None:
    """The transient provider error in a body that is an error, not a completion: an `error`
    object with no `choices`, whose code `_may_pass`. None for anything else, which then fails
    exactly as it did before."""
    if not isinstance(body, dict) or body.get("choices"):
        return None
    err = body.get("error")
    return err if isinstance(err, dict) and err and _may_pass(err) else None


def _provider_error(err: dict, url: Any) -> openai.InternalServerError:
    """An in-band provider error as the 502 it stands for, so every caller treats it as a
    transient API error (TRANSIENT_API_ERRORS). The provider's message, code and metadata stay in
    the text and the body."""
    text = (
        f"in-band provider error (code {err.get('code')}): "
        f"{err.get('message') or 'no message'}; metadata={err.get('metadata')}"
    )
    response = httpx.Response(502, request=httpx.Request("POST", str(url)))
    return openai.InternalServerError(text, response=response, body=err)


class OpenRouterChat(ChatOpenAI):
    """ChatOpenAI with two OpenRouter fixes.

    It keeps OpenRouter's raw `usage` (including the real `cost`) on streamed calls.
    langchain-openai turns `chunk["usage"]` into token counts only, so the cost is lost (R12);
    here it is also copied to `response_metadata["token_usage"]`, where the non-streamed path
    already puts it and where `extract_usage` and the prompt log look.

    It turns an in-band provider error (HTTP 200 whose body is `{"error": {...}, "choices": null}`)
    into `openai.InternalServerError`, so the guard and router retry it, the judge fails closed
    and the extractor counts a failed attempt. No single seam sees every shape, so three do:
    - `_create_chat_result`: a plain non-streamed call, before langchain raises a bare ValueError;
    - `_agenerate`: a structured non-streamed call, where openai's `parse` fails with a TypeError
      on `choices=None` and langchain attaches the raw response to the exception;
    - `_astream`: any streamed call, where openai's SSE reader raises a bare `openai.APIError`
      carrying the error object as its body.
    Only an error that may pass on a retry is translated (`_may_pass`); an explicit 4xx is left
    as it was. `_create_chat_result` also serves the sync plain path; the structured and streamed
    seams are async only, since nothing in the app calls a chat model synchronously."""

    def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info):
        gen = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if gen is not None and chunk.get("usage"):
            gen.message.response_metadata["token_usage"] = dict(chunk["usage"])
        return gen

    def _chat_url(self) -> str:
        return f"{str(self.root_async_client.base_url).rstrip('/')}/chat/completions"

    def _create_chat_result(self, response: Any, generation_info: dict | None = None):
        # Read the two fields only: dumping a structured completion would warn about `parsed`.
        body = response if isinstance(response, dict) else {
            "error": getattr(response, "error", None), "choices": getattr(response, "choices", None)
        }
        if (err := _in_band_error(body)) is not None:
            raise _provider_error(err, self._chat_url())
        return super()._create_chat_result(response, generation_info)

    async def _agenerate(self, *args: Any, **kwargs: Any):
        try:
            return await super()._agenerate(*args, **kwargs)
        except openai.APIError:
            raise
        except Exception as exc:
            raw = getattr(exc, "response", None)
            try:
                body = raw.json() if raw is not None else None
            except Exception:
                body = None
            if (err := _in_band_error(body)) is not None:
                raise _provider_error(err, raw.request.url) from exc
            raise

    async def _astream(self, *args: Any, **kwargs: Any) -> AsyncIterator:
        try:
            async for chunk in super()._astream(*args, **kwargs):
                yield chunk
        except openai.APIError as exc:
            # Only the bare class: its subclasses are real HTTP status and connection errors.
            if type(exc) is openai.APIError and (err := _in_band_error({"error": exc.body})):
                raise _provider_error(err, exc.request.url) from exc
            raise


def make_chat_model(
    settings: Settings,
    *,
    model: str | None = None,
    temperature: float = 0.0,
    provider: str | None = None,
) -> OpenRouterChat:
    return OpenRouterChat(
        model=model or settings.chat_model,
        temperature=temperature,
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key.get_secret_value(),
        max_retries=3,
        timeout=60,
        stream_usage=True,
        extra_body={
            "provider": {"order": [provider] if provider else settings.provider_order, "allow_fallbacks": False},
            "usage": {"include": True},
        },
    )


def make_gemini_model(
    settings: Settings, *, http_async_client: httpx.AsyncClient | None = None
) -> ChatOpenAI:
    """Gemini over its OpenAI-compatible endpoint. Configured-only (R11.G9): nothing at runtime
    calls this, `make_model_for` never returns it and the allowlist never lists it; only the
    tests build it, with a fake key and a mock transport. No retries, so a 429 or 503 is one
    request."""
    key = settings.gemini_api_key
    if key is None or not key.get_secret_value():
        raise ValueError("GEMINI_API_KEY is not set")
    return ChatOpenAI(
        model=GEMINI_MODEL,
        base_url=GEMINI_BASE_URL,
        api_key=key.get_secret_value(),
        max_retries=0,
        timeout=60,
        http_async_client=http_async_client,
    )


def make_embeddings(settings: Settings) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=settings.embed_model,
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key.get_secret_value(),
        check_embedding_ctx_length=False,
    )
