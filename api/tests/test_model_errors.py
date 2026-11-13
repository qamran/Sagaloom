"""Model-call failures in words a user can act on (sagaloom/model_errors.py)."""

import httpx
import openai
import pytest

from sagaloom.model_errors import ModelCallError, classify, describe, failure_line

URL = "https://openrouter.ai/api/v1/chat/completions"
SO = "so I couldn't reply"


def status_error(cls, status: int, message: str, model: str | None = "openai/gpt-x"):
    request = httpx.Request("POST", URL, json={"model": model} if model else None)
    response = httpx.Response(status, request=request)
    return cls(message, response=response, body={"error": {"message": message, "code": status}})


def payment_error():
    return status_error(openai.APIStatusError, 402, "Insufficient credits")


CASES = [
    # (exception, kind, retryable, words the message must hold)
    (status_error(openai.NotFoundError, 404, "No endpoints found for openai/gpt-x."), "gone", False,
     ["The chat model (openai/gpt-x) is no longer available on OpenRouter", SO, "Studio → Models and providers"]),
    (status_error(openai.BadRequestError, 400, "openai/gpt-x is not a valid model ID"), "gone", False,
     ["no longer available", "Studio"]),
    (status_error(openai.PermissionDeniedError, 403, "Model not allowed by your guardrail"), "blocked", False,
     ["OpenRouter refused the chat model (openai/gpt-x)", "not allowed", "choose an allowed model"]),
    (payment_error(), "no_credit", False, ["out of credit", "openrouter.ai"]),
    (status_error(openai.AuthenticationError, 401, "No auth credentials found"), "bad_key", False,
     ["did not accept the API key", "OPENROUTER_API_KEY"]),
    (status_error(openai.RateLimitError, 429, "Rate limit exceeded"), "rate_limited", True, ["limiting requests", "Wait"]),
    (status_error(openai.BadRequestError, 400, "max_tokens too large"), "rejected", False, ["rejected the request", "(400)"]),
    (status_error(openai.InternalServerError, 502, "provider returned error"), "down", True, ["provider had an error"]),
    (openai.APITimeoutError(request=httpx.Request("POST", URL)), "timeout", True, ["took too long"]),
    (openai.APIConnectionError(request=httpx.Request("POST", URL)), "network", True, ["could not reach OpenRouter"]),
]


@pytest.mark.parametrize(("exc", "kind", "retryable", "words"), CASES, ids=[c[1] + str(i) for i, c in enumerate(CASES)])
def test_each_cause_is_named_with_its_next_step(exc, kind, retryable, words):
    assert classify(exc).kind == kind
    message, again = describe(exc, "agent", SO)
    assert again is retryable
    for w in words:
        assert w.lower() in message.lower(), (w, message)
    # "Try again" only where a retry can help.
    assert ("try again" in message.lower()) == (retryable or kind == "no_credit")


def test_the_model_comes_from_the_call_site_when_the_request_does_not_name_it():
    exc = status_error(openai.NotFoundError, 404, "gone", model=None)
    message, _ = describe(exc, "judge", "so the check could not run", model="google/gemini-x")
    assert message.startswith("The contradiction judge's model (google/gemini-x) is no longer available")


def test_guard_and_router_point_to_the_env_not_the_studio_dropdown():
    exc = status_error(openai.NotFoundError, 404, "gone")
    for role in ("guard", "router"):
        message, _ = describe(exc, role, "so I didn't act on it")
        assert "GUARD_MODEL in api/.env" in message and "Models and providers" not in message


def test_a_wrapped_call_error_keeps_its_role_model_and_cause():
    original = status_error(openai.NotFoundError, 404, "gone", model=None)
    wrapped = ModelCallError("agent", "openai/gpt-y", original)
    assert classify(wrapped).kind == "gone"
    assert "(openai/gpt-y)" in describe(wrapped, "agent", SO)[0]


def test_a_non_api_error_is_not_a_model_failure():
    assert classify(ValueError("bad")) is None
    message, again = describe(ValueError("bad"), "agent", SO)
    assert message == "Something went wrong, so I couldn't reply. Please try again." and again


def test_failure_line_is_short_and_keeps_openrouters_words():
    line = failure_line(status_error(openai.NotFoundError, 404, "No endpoints found for openai/gpt-x. " + "x" * 400))
    assert line.startswith("gone 404: No endpoints found for openai/gpt-x.")
    assert len(line) < 200
    assert failure_line(ValueError("boom")) == "ValueError: boom"
