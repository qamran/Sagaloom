"""One structured-output call with a bounded retry, shared by the guard, the router and the
contradiction judge.

An invalid reply (the model answered, but not with the schema) is always retried once. A
transient API error (connection, timeout, rate limit, 5xx) is retried only when the caller asks.
Everything else, including a 4xx client error, propagates at once: retrying it cannot help.
"""

import logging
from typing import Any, Protocol, TypeVar

import openai
from langchain_core.exceptions import OutputParserException
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

MAX_ATTEMPTS = 2  # "retry once"


class ChatModelLike(Protocol):
    """The slice of a chat model that the tools and the structured-output callers use."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any: ...
    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any: ...
    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any: ...


def _invalid_reply_errors() -> tuple[type[BaseException], ...]:
    """Exceptions meaning "the model replied, but not with a usable structured reply".

    ChatOpenAI's json_schema parser raises a bare ValueError (no `parsed` field) or
    OpenAIRefusalError; the openai SDK raises the finish-reason errors. Imported
    defensively so a different SDK version can't break this module.
    """
    errors: list[type[BaseException]] = [OutputParserException, ValidationError, ValueError]
    try:
        from langchain_openai.chat_models.base import OpenAIRefusalError

        errors.append(OpenAIRefusalError)
    except ImportError:  # pragma: no cover
        pass
    for name in ("LengthFinishReasonError", "ContentFilterFinishReasonError"):
        if isinstance(cls := getattr(openai, name, None), type):
            errors.append(cls)
    return tuple(errors)


INVALID_REPLY = _invalid_reply_errors()

TRANSIENT_API_ERRORS = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.InternalServerError,
)


class InvalidReply(ValueError):
    """The model gave an unusable reply on every attempt."""


async def ask_structured(
    model: ChatModelLike,
    schema: type[T],
    messages: list,
    *,
    what: str,
    retry_transient: bool,
) -> T:
    """Up to MAX_ATTEMPTS calls for a valid `schema` reply.

    Raises InvalidReply (chained to the last cause) after the last invalid reply. With
    `retry_transient`, a TRANSIENT_API_ERRORS exception is retried and re-raised after the last
    attempt. Any other exception propagates at once."""
    structured = model.with_structured_output(schema)
    last: BaseException | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            out = await structured.ainvoke(messages)
            if isinstance(out, dict):
                out = schema.model_validate(out)
            if isinstance(out, schema):
                return out
            last = ValueError(f"{what} returned no usable reply ({type(out).__name__})")
            log.warning("%s attempt %d: no structured output", what, attempt)
        except INVALID_REPLY as exc:
            last = exc
            log.warning("%s attempt %d: invalid reply (%s)", what, attempt, type(exc).__name__)
        except TRANSIENT_API_ERRORS as exc:
            if not retry_transient or attempt == MAX_ATTEMPTS:
                raise
            log.warning("%s attempt %d: %s, retrying", what, attempt, type(exc).__name__)
    raise InvalidReply(f"{what} gave no valid reply after {MAX_ATTEMPTS} attempts") from last
