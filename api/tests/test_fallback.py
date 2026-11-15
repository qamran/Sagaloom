"""A role's named fallback model (R11.G11, sagaloom/fallback.py): which failures fall back, what
the fallback gets, the settings that choose it, and how a role's model is wired."""

import json

import httpx
import openai
import pytest
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from langchain_openai import ChatOpenAI
from stubs import StubLLM

from sagaloom.config import Settings
from sagaloom.fallback import PARTIAL_OUTPUT, FallbackModel, should_fall_back
from sagaloom.guard import GuardVerdict
from sagaloom.llm import make_chat_model
from sagaloom.model_errors import ModelCallError, describe
from sagaloom.model_settings import ModelSettings, validate_role_models
from sagaloom.web.app import make_model_for

URL = "https://openrouter.ai/api/v1/chat/completions"
PRIMARY, FALLBACK = "openai/gpt-6-luna", "anthropic/claude-haiku-5.5"


def api_error(cls, status: int, message: str, model: str = PRIMARY):
    request = httpx.Request("POST", URL, json={"model": model})
    return cls(message, response=httpx.Response(status, request=request), body={"error": {"message": message, "code": status}})


def gone():
    return api_error(openai.NotFoundError, 404, f"No endpoints found for {PRIMARY}.")


def blocked():
    return api_error(openai.PermissionDeniedError, 403, "Model not allowed by your guardrail")


def down():
    return api_error(openai.InternalServerError, 502, "provider returned error")


def settings(**kw) -> Settings:
    return Settings(_env_file=None, openrouter_api_key="k", api_shared_secret="s", **kw)


# ---------- which failures fall back ----------

FALLS_BACK = [gone(), api_error(openai.BadRequestError, 400, f"{PRIMARY} is not a valid model ID"), blocked(), down()]
STAYS = [
    api_error(openai.APIStatusError, 402, "Insufficient credits"),  # the fallback is billed to the same account
    api_error(openai.AuthenticationError, 401, "No auth credentials found"),  # same key
    api_error(openai.RateLimitError, 429, "Rate limit exceeded"),
    api_error(openai.BadRequestError, 400, "max_tokens too large"),  # our request: would fail again
    openai.APITimeoutError(request=httpx.Request("POST", URL)),
    openai.APIConnectionError(request=httpx.Request("POST", URL)),  # our network
    ValueError("not a model API error"),
]


@pytest.mark.parametrize("exc", FALLS_BACK, ids=["gone404", "gone400", "blocked", "down"])
def test_withdrawn_blocked_or_failing_models_fall_back(exc):
    assert should_fall_back(exc)


@pytest.mark.parametrize("exc", STAYS, ids=["no_credit", "bad_key", "rate_limited", "rejected", "timeout", "network", "other"])
def test_other_failures_do_not_fall_back(exc):
    assert not should_fall_back(exc)


def test_a_reply_that_already_streamed_text_is_not_replayed():
    exc = down()
    setattr(exc, PARTIAL_OUTPUT, True)
    assert not should_fall_back(exc)


# ---------- what the fallback gets ----------


async def test_fallback_answers_the_same_request_with_a_note_in_its_metadata():
    primary = StubLLM(gone())
    fallback = StubLLM(GuardVerdict(verdict="safe", reason="fallback"))
    model = FallbackModel(primary, fallback, primary_id=PRIMARY, fallback_id=FALLBACK)
    out = await model.with_structured_output(GuardVerdict).ainvoke(["the message"], {"metadata": {"thread_id": "t1"}})
    assert out.reason == "fallback"
    assert primary.schemas == fallback.schemas == [GuardVerdict]  # the same chain on both
    assert fallback.prompts == primary.prompts == [["the message"]]
    meta = fallback.configs[0]["metadata"]
    assert meta["fallback_for"] == PRIMARY and meta["fallback_reason"].startswith("gone 404: No endpoints found")
    assert meta["thread_id"] == "t1"  # the call's own metadata is kept
    assert "fallback_for" not in (primary.configs[0] or {}).get("metadata", {})


async def test_primary_success_never_calls_the_fallback():
    fallback = StubLLM(AssertionError("must not be called"))
    model = FallbackModel(StubLLM(GuardVerdict(verdict="safe", reason="ok")), fallback, primary_id=PRIMARY, fallback_id=FALLBACK)
    assert (await model.with_structured_output(GuardVerdict).ainvoke(["hi"])).reason == "ok"
    assert fallback.prompts == []


async def test_an_error_that_cannot_fall_back_is_raised_untouched():
    credit = STAYS[0]
    fallback = StubLLM(GuardVerdict(verdict="safe", reason="x"))
    model = FallbackModel(StubLLM(credit), fallback, primary_id=PRIMARY, fallback_id=FALLBACK)
    with pytest.raises(openai.APIStatusError) as caught:
        await model.ainvoke(["hi"])
    assert caught.value is credit and fallback.prompts == []


async def test_when_both_fail_the_message_names_both_models():
    model = FallbackModel(StubLLM(gone()), StubLLM(down()), primary_id=PRIMARY, fallback_id=FALLBACK)
    with pytest.raises(openai.NotFoundError) as caught:
        await model.ainvoke(["hi"])
    message, retryable = describe(ModelCallError("agent", PRIMARY, caught.value), "agent", "so I couldn't reply")
    assert message.startswith(f"The chat model ({PRIMARY}) is no longer available on OpenRouter")
    assert message.endswith(f"The fallback model ({FALLBACK}) failed too: down 502: provider returned error.")
    assert retryable is False  # it is the primary's failure that the admin must fix


def test_the_model_name_is_the_primarys():
    class Named:
        model_name = PRIMARY

    assert FallbackModel(Named(), Named(), primary_id=PRIMARY, fallback_id=FALLBACK).model_name == PRIMARY


# ---------- the streamed reply marks text it already sent ----------


def _stream_then_fail(chunks: list[str]):
    async def astream(self, *args, **kwargs):
        for text in chunks:
            yield ChatGenerationChunk(message=AIMessageChunk(content=text))
        raise down()

    return astream


@pytest.mark.parametrize(("chunks", "partial"), [(["Velmar has"], True), ([""], False), ([], False)])
async def test_openrouter_chat_marks_a_stream_that_failed_after_sending_text(monkeypatch, chunks, partial):
    monkeypatch.setattr(ChatOpenAI, "_astream", _stream_then_fail(chunks))
    model = make_chat_model(settings())
    with pytest.raises(openai.InternalServerError) as caught:
        async for _ in model._astream([]):
            pass
    assert getattr(caught.value, PARTIAL_OUTPUT) is partial
    assert should_fall_back(caught.value) is (not partial)


# ---------- settings ----------


def test_every_role_defaults_to_the_built_in_fallback(tmp_path):
    ms = ModelSettings(tmp_path / "m.json", settings())
    assert ms.get_fallbacks() == {r: FALLBACK for r in ("agent", "judge", "extractor", "guard")}
    assert ModelSettings(tmp_path / "n.json", settings(fallback_model="")).get_fallbacks()["agent"] is None


def test_a_fallback_is_chosen_per_role_and_kept_beside_the_role_models(tmp_path):
    path = tmp_path / "m.json"
    ms = ModelSettings(path, settings())
    ms.set_fallback("judge", "google/gemini-3.8-flash")
    ms.set_fallback("guard", None)
    ms.set_model("agent", "openai/gpt-6.1-terra")  # a role switch keeps the fallbacks
    assert ms.get_fallbacks()["judge"] == "google/gemini-3.8-flash"
    assert ms.get_fallbacks()["guard"] is None and ms.get_fallbacks()["agent"] == FALLBACK
    assert ms.get_model_settings()["agent"] == "openai/gpt-6.1-terra"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["fallbacks"] == {"judge": "google/gemini-3.8-flash", "guard": ""} and saved["agent"] == "openai/gpt-6.1-terra"
    with pytest.raises(ValueError, match="allowlist"):
        ms.set_fallback("judge", "evil/not-allowed")
    with pytest.raises(ValueError, match="unknown role"):
        ms.set_fallback("nobody", FALLBACK)  # type: ignore[arg-type]


def test_a_fallback_off_the_allowlist_stops_the_api_at_start():
    with pytest.raises(ValueError, match="FALLBACK_MODEL=evil/not-allowed"):
        validate_role_models(settings(fallback_model="evil/not-allowed"))
    validate_role_models(settings(fallback_model=""))  # none is fine


# ---------- wiring ----------


def test_a_role_with_a_different_fallback_gets_both(tmp_path):
    class Fake:
        def __init__(self, role, model):
            self.model_name, self.metadata = model, {}

    ms = ModelSettings(tmp_path / "m.json", settings())
    model_for = make_model_for(settings(), ms, lambda role, model: Fake(role, model))
    agent = model_for("agent")
    assert isinstance(agent, FallbackModel) and model_for("agent") is agent
    assert (agent.primary.model_name, agent.fallback.model_name) == (PRIMARY, FALLBACK)
    assert agent.primary.metadata["role"] == agent.fallback.metadata["role"] == "agent"  # cost by step keeps the role
    router = model_for("router")  # the router follows the guard's model and fallback
    assert isinstance(router, FallbackModel) and router.fallback.metadata["role"] == "router"

    ms.set_fallback("judge", None)
    ms.set_fallback("extractor", PRIMARY)  # the same model as the role's: nothing to fall back to
    assert not isinstance(model_for("judge"), FallbackModel)
    assert not isinstance(model_for("extractor"), FallbackModel)
