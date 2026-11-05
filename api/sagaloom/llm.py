import httpx
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from sagaloom.config import Settings
from sagaloom.studio import GEMINI_MODEL

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class OpenRouterChat(ChatOpenAI):
    """ChatOpenAI that keeps OpenRouter's raw `usage` (including the real `cost`) on streamed
    calls. langchain-openai turns `chunk["usage"]` into token counts only, so the cost is lost
    (R12); here it is also copied to `response_metadata["token_usage"]`, where the non-streamed
    path already puts it and where `extract_usage` and the prompt log look."""

    def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info):
        gen = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if gen is not None and chunk.get("usage"):
            gen.message.response_metadata["token_usage"] = dict(chunk["usage"])
        return gen


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
