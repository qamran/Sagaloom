from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from sagaloom.config import Settings


def make_chat_model(
    settings: Settings, *, model: str | None = None, temperature: float = 0.0
) -> ChatOpenAI:
    return ChatOpenAI(
        model=model or settings.chat_model,
        temperature=temperature,
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key.get_secret_value(),
        max_retries=3,
        timeout=60,
        stream_usage=True,
        extra_body={
            "provider": {"order": settings.provider_order, "allow_fallbacks": False},
            "usage": {"include": True},
        },
    )


def make_embeddings(settings: Settings) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=settings.embed_model,
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key.get_secret_value(),
        check_embedding_ctx_length=False,
    )
