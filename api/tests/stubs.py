"""The one structured-output model stub every test shares (re-exported as `fakes.StubLLM`).
Importable as `stubs` from any test directory (tests/ is on sys.path through its rootdir
conftest)."""

import json

from langchain_core.messages import AIMessage
from pydantic import BaseModel, ValidationError

from sagaloom.auth import AuthError, Claims, ClerkProfile


def as_raw(reply, schema) -> dict:
    """`reply` as LangChain's `include_raw=True` answer: the raw message, then the parse (or the
    parsing error when `reply` doesn't validate against `schema`)."""
    if isinstance(reply, BaseModel):
        return {"raw": AIMessage(content=reply.model_dump_json()), "parsed": reply, "parsing_error": None}
    raw = AIMessage(content=json.dumps(reply))
    try:
        return {"raw": raw, "parsed": schema.model_validate(reply), "parsing_error": None}
    except ValidationError as exc:
        return {"raw": raw, "parsed": None, "parsing_error": exc}


class StubLLM:
    """A structured-output model stub. `reply` is a value, an exception to raise, or a callable of
    the messages returning either. With `include_raw=True` it answers as LangChain does:
    {"raw", "parsed", "parsing_error"} (a reply that already has that shape is returned as is).
    Every schema, kwargs, prompt and config it sees is recorded; binding tools fails the test."""

    def __init__(self, reply):
        self.reply = reply
        self.schemas: list = []
        self.kwargs: list = []
        self.prompts: list = []
        self.configs: list = []

    def bind_tools(self, *a, **kw):
        raise AssertionError("bind_tools must never be called on a structured-output stub")

    def with_structured_output(self, schema, **kwargs):
        self.schemas.append(schema)
        self.kwargs.append(kwargs)
        return self

    async def ainvoke(self, messages, config=None):
        self.prompts.append(messages)
        self.configs.append(config)
        reply = self.reply(messages) if callable(self.reply) else self.reply
        if isinstance(reply, Exception):
            raise reply
        if not (self.kwargs and self.kwargs[-1].get("include_raw")) or (isinstance(reply, dict) and "raw" in reply):
            return reply
        return as_raw(reply, self.schemas[-1])


class FakeVerifier:
    """A `TokenVerifier` that maps token strings to subs; any other token raises `AuthError`.
    `expire_after`, when set, rejects every call after that many (a token that expired)."""

    def __init__(self, tokens: dict[str, str] | None = None, expire_after: int | None = None):
        self.tokens = dict(tokens or {})
        self.expire_after = expire_after
        self.calls = 0

    def verify(self, token: str):
        self.calls += 1
        if self.expire_after is not None and self.calls > self.expire_after:
            raise AuthError("invalid token: ExpiredSignatureError")
        if token not in self.tokens:
            raise AuthError("invalid token: DecodeError")
        return Claims(sub=self.tokens[token])


class FakeDirectory:
    """A `ProfileDirectory` with a verified `<sub>@example.test` profile for any user unless
    `profiles` says otherwise. Records the ids it was asked for."""

    def __init__(self, profiles: dict | None = None):
        self.profiles = dict(profiles or {})
        self.fetched: list[str] = []

    async def fetch(self, user_id: str):
        self.fetched.append(user_id)
        return self.profiles.get(user_id) or ClerkProfile(
            email=f"{user_id}@example.test", email_verified=True, display_name=user_id
        )


# The default signed-in user of the API tests.
USER_A = "user_a"
TOKEN_A = "tok-a"


def bearer(token: str = TOKEN_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
