"""The shared structured-output retry helper. No real LLM calls."""

import httpx
import openai
import pytest
from pydantic import BaseModel

from sagaloom.structured import (
    INVALID_REPLY,
    MAX_ATTEMPTS,
    TRANSIENT_API_ERRORS,
    InvalidReply,
    ask_structured,
)


class Out(BaseModel):
    n: int


class Seq:
    """Replies in order; an Exception in the list is raised."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0

    def with_structured_output(self, schema, **kwargs):
        return self

    async def ainvoke(self, messages, config=None):
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _conn() -> openai.APIConnectionError:
    return openai.APIConnectionError(request=httpx.Request("POST", "http://x"))


def _status(code: int) -> openai.APIStatusError:
    req = httpx.Request("POST", "http://x")
    return openai.APIStatusError("bad", response=httpx.Response(code, request=req), body=None)


async def ask(model, **kw):
    kw.setdefault("retry_transient", False)
    return await ask_structured(model, Out, ["m"], what="Test", **kw)


def test_public_constants():
    assert MAX_ATTEMPTS == 2
    assert ValueError in INVALID_REPLY
    assert openai.RateLimitError in TRANSIENT_API_ERRORS


async def test_retries_once_after_invalid_reply():
    m = Seq(None, Out(n=1))
    assert (await ask(m)).n == 1 and m.calls == 2


async def test_raises_invalid_reply_after_two():
    m = Seq(None, ValueError("bad"))
    with pytest.raises(InvalidReply) as info:
        await ask(m)
    assert m.calls == 2 and isinstance(info.value.__cause__, ValueError)


async def test_retries_transient_error_when_asked():
    m = Seq(_conn(), Out(n=2))
    assert (await ask(m, retry_transient=True)).n == 2 and m.calls == 2


async def test_transient_error_reraised_after_last_attempt():
    m = Seq(_conn(), _conn())
    with pytest.raises(openai.APIConnectionError):
        await ask(m, retry_transient=True)
    assert m.calls == 2


async def test_does_not_retry_transient_when_not_asked():
    m = Seq(_conn(), Out(n=2))
    with pytest.raises(openai.APIConnectionError):
        await ask(m)
    assert m.calls == 1


async def test_client_error_is_not_retried():
    m = Seq(_status(400), Out(n=1))
    with pytest.raises(openai.APIStatusError):
        await ask(m, retry_transient=True)
    assert m.calls == 1


async def test_dict_reply_is_validated():
    m = Seq({"n": 3})
    assert (await ask(m)).n == 3
    bad = Seq({"n": "x"}, {"n": "y"})
    with pytest.raises(InvalidReply):
        await ask(bad)
    assert bad.calls == 2
