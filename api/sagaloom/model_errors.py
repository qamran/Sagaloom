"""What went wrong with a model call, in words a user can act on.

Every model call goes through OpenRouter, pinned to one provider with no fallbacks. When a call
fails, the step that made it (guard, router, chat agent, contradiction judge, fact extractor)
used to say only "unavailable, try again", which is wrong advice when the model was removed, the
key may not use it, or the account is out of credit. `describe` names the step, the model, the
cause and the next step, and says whether a retry can help. `failure_line` is the short form
kept on the prompt record (Under the hood, Studio → Guardrails).
"""

import json
from typing import Any, Literal

import openai
from pydantic import BaseModel

Role = Literal["agent", "judge", "extractor", "guard", "router"]
Kind = Literal["gone", "blocked", "no_credit", "bad_key", "rate_limited", "rejected", "timeout", "network", "down"]

ROLE_NAMES: dict[str, str] = {
    "agent": "chat model",
    "judge": "contradiction judge's model",
    "extractor": "fact extractor's model",
    "guard": "input guard's model",
    "router": "router's model (the input guard's model)",
}

# Where the model for each role is chosen. The guard and the router are set in the API's env.
_STUDIO = "An admin can choose another model in Studio → Models and providers."
_ENV = "An admin can set GUARD_MODEL in api/.env, or switch the input guard off in Studio → Guardrails."
CHOOSE_ANOTHER: dict[str, str] = {
    "agent": _STUDIO, "judge": _STUDIO, "extractor": _STUDIO, "guard": _ENV, "router": _ENV,
}

# OpenRouter's wording for a model it no longer serves (or not from the pinned provider).
_GONE_WORDS = ("not a valid model", "no endpoints", "model not found", "does not exist", "is not available",
               "no allowed providers", "deprecated")
DETAIL_CHARS = 160


class ModelFailure(BaseModel):
    kind: Kind
    retryable: bool
    status: int | None = None
    detail: str = ""  # OpenRouter's own message, shortened


class ModelCallError(Exception):
    """A failed model call, with the role that made it and its model, for the stream's error
    message. Raised from the original exception, which stays as `__cause__`."""

    def __init__(self, role: Role, model: str | None, original: BaseException):
        super().__init__(f"{role} model call failed: {type(original).__name__}")
        self.role = role
        self.model = model
        self.original = original


def model_name(model: Any) -> str | None:
    """The model id of a chat model (or a `RoleModel` forwarding to one), if it says."""
    for attr in ("model_name", "model"):
        try:
            value = getattr(model, attr, None)
        except Exception:
            value = None
        if isinstance(value, str) and value:
            return value
    return None


def _detail(exc: openai.APIError) -> str:
    body = exc.body
    text = ""
    if isinstance(body, dict):
        err = body.get("error") if isinstance(body.get("error"), dict) else body
        text = str(err.get("message") or "")
    text = text or str(getattr(exc, "message", "") or exc)
    text = " ".join(text.split())
    return text[:DETAIL_CHARS] + ("…" if len(text) > DETAIL_CHARS else "")


def _requested_model(exc: openai.APIError) -> str | None:
    """The model named in the failed request's body, when the request is kept."""
    try:
        data = json.loads(exc.request.content or b"{}")
    except Exception:
        return None
    model = data.get("model") if isinstance(data, dict) else None
    return model if isinstance(model, str) and model else None


def classify(exc: BaseException) -> ModelFailure | None:
    """The cause of a failed model call; None when `exc` is not a model API error."""
    if isinstance(exc, ModelCallError):
        exc = exc.original
    if not isinstance(exc, openai.APIError):
        return None
    if isinstance(exc, openai.APITimeoutError):
        return ModelFailure(kind="timeout", retryable=True, detail=_detail(exc))
    if isinstance(exc, openai.APIConnectionError):
        return ModelFailure(kind="network", retryable=True, detail=_detail(exc))
    status = getattr(exc, "status_code", None)
    detail = _detail(exc)
    low = detail.lower()
    if status == 404 or (status == 400 and any(w in low for w in _GONE_WORDS)):
        return ModelFailure(kind="gone", retryable=False, status=status, detail=detail)
    if status == 401:
        return ModelFailure(kind="bad_key", retryable=False, status=status, detail=detail)
    if status == 402:
        return ModelFailure(kind="no_credit", retryable=False, status=status, detail=detail)
    if status == 403:
        return ModelFailure(kind="blocked", retryable=False, status=status, detail=detail)
    if status == 429:
        return ModelFailure(kind="rate_limited", retryable=True, status=status, detail=detail)
    if isinstance(status, int) and 400 <= status < 500:
        return ModelFailure(kind="rejected", retryable=False, status=status, detail=detail)
    return ModelFailure(kind="down", retryable=True, status=status, detail=detail)


def describe(exc: BaseException, role: Role, consequence: str, model: str | None = None) -> tuple[str, bool]:
    """(message, retryable) for a failed call: which step and model, the cause, what it meant
    (`consequence`, e.g. "so I couldn't reply"), and what to do. A non-API error gets a plain
    "something went wrong" with the consequence."""
    failure = classify(exc)
    original = exc.original if isinstance(exc, ModelCallError) else exc
    if isinstance(exc, ModelCallError):
        model = model or exc.model
    if isinstance(original, openai.APIError):
        model = _requested_model(original) or model
    who = f"The {ROLE_NAMES[role]}" + (f" ({model})" if model else "")
    if failure is None:
        return f"Something went wrong, {consequence}. Please try again.", True
    change = CHOOSE_ANOTHER[role]
    text = {
        "gone": f"{who} is no longer available on OpenRouter from its provider, {consequence}. {change}",
        "blocked": f"OpenRouter refused the {ROLE_NAMES[role]}" + (f" ({model})" if model else "")
        + f": this API key is not allowed to use it, {consequence}. {change.replace('another', 'an allowed')}",
        "no_credit": f"The OpenRouter account is out of credit, {consequence}. Add credit at openrouter.ai, then try again.",
        "bad_key": f"OpenRouter did not accept the API key, {consequence}. An admin can check OPENROUTER_API_KEY in api/.env.",
        "rate_limited": f"OpenRouter is limiting requests to the {ROLE_NAMES[role]} right now, {consequence}. Wait a moment, then try again.",
        "rejected": f"OpenRouter rejected the request to the {ROLE_NAMES[role]}"
        + (f" ({model})" if model else "") + f" ({failure.status}), {consequence}. {change}",
        "timeout": f"{who} took too long to answer, {consequence}. Try again in a moment.",
        "network": f"Sagaloom could not reach OpenRouter, {consequence}. Check the internet connection, then try again.",
        "down": f"{who}'s provider had an error, {consequence}. Try again in a moment.",
    }[failure.kind]
    return text, failure.retryable


def failure_line(exc: BaseException) -> str:
    """The short form for a prompt record: kind, status and OpenRouter's own words."""
    failure = classify(exc)
    if failure is None:
        return f"{type(exc).__name__}: {str(exc)[:DETAIL_CHARS]}"
    status = f" {failure.status}" if failure.status else ""
    return f"{failure.kind}{status}: {failure.detail}" if failure.detail else f"{failure.kind}{status}"
