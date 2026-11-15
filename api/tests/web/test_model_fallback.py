"""The named fallback model through the app (R11.G11): the chat turn, its prompt records and turn
usage, Studio → Guardrails, and the settings routes."""

import httpx
import openai
from fakes import FALLBACK_MODEL, FALLBACK_PRIMARY, USER_A, names
from langchain_core.messages import AIMessage

from sagaloom.promptlog import PromptRecord

URL = "https://openrouter.ai/api/v1/chat/completions"


def api_error(cls, status: int, message: str, model: str = FALLBACK_PRIMARY):
    request = httpx.Request("POST", URL, json={"model": model})
    return cls(message, response=httpx.Response(status, request=request), body={"error": {"message": message, "code": status}})


def gone():
    return api_error(openai.NotFoundError, 404, f"No endpoints found for {FALLBACK_PRIMARY}.")


async def test_a_removed_chat_model_is_answered_by_the_fallback(make_env):
    env = make_env([gone()], agent_fallback=[AIMessage(content="Velmar has one moon.")])
    tid = await env.new_thread()
    _, events = await env.send(tid)
    assert "error" not in names(events) and "done" in names(events)
    assert "".join(d.get("text", "") for e, d in events if e == "token") == "Velmar has one moon."
    # The live stream says which model answered instead, and why.
    [request] = [d for e, d in events if e == "llm_request" and d.get("fallback_for")]
    assert request["fallback_for"] == FALLBACK_PRIMARY and request["fallback_reason"].startswith("gone 404")
    # Under the hood keeps both calls: the failed one with its cause, then the fallback's.
    failed, answered = env.deps.promptlog.list(tid)[-2:]
    assert failed.response["error"].startswith("gone 404") and failed.fallback_for is None
    assert answered.fallback_for == FALLBACK_PRIMARY and answered.fallback_reason.startswith("gone 404")
    assert answered.response["content"] == "Velmar has one moon."
    # The thread's turn usage lists the fallback for the turn's cost line.
    body = (await env.client.get(f"/api/threads/{tid}")).json()
    [use] = body["turns"][-1]["fallbacks"]
    assert use["replaced"] == FALLBACK_PRIMARY and use["ok"] is True and use["reason"].startswith("gone 404")


async def test_out_of_credit_does_not_fall_back(make_env):
    env = make_env([api_error(openai.APIStatusError, 402, "Insufficient credits")],
                   agent_fallback=[AIMessage(content="must not run")])
    tid = await env.new_thread()
    _, events = await env.send(tid)
    [err] = [d for e, d in events if e == "error"]
    assert err["message"].startswith("The OpenRouter account is out of credit")
    assert "fallback" not in err["message"]
    assert not any(r.fallback_for for r in env.deps.promptlog.list(tid))


async def test_when_the_fallback_fails_too_the_error_names_both(make_env):
    down = api_error(openai.InternalServerError, 502, "provider returned error", model=FALLBACK_MODEL)
    env = make_env([gone()], agent_fallback=[down])
    tid = await env.new_thread()
    _, events = await env.send(tid)
    [err] = [d for e, d in events if e == "error"]
    assert err["message"].startswith(f"The chat model ({FALLBACK_PRIMARY}) is no longer available")
    assert f"The fallback model ({FALLBACK_MODEL}) failed too: down 502" in err["message"]
    assert err["retryable"] is False


def _guard_record(env, rid, model, response, *, run_id="turn1", fallback_for=None, started="2026-11-15T10:00:00+00:00"):
    rec = PromptRecord(
        id=rid, thread_id="t1", run_id=run_id, provider="openrouter", model=model, role="guard",
        fallback_for=fallback_for, fallback_reason="gone 404: x" if fallback_for else None,
        request={"messages": [{"role": "user", "content": "<untrusted_data>hello</untrusted_data>"}], "tools": []},
        started_at=started,
    )
    env.deps.promptlog.add(rec, user_id=USER_A)
    env.deps.promptlog.complete(rid, response)


async def test_guardrails_shows_the_fallbacks_verdict_not_a_phantom_block(make_env):
    env = make_env()
    _guard_record(env, "a", FALLBACK_PRIMARY, {"content": "", "tool_calls": [], "error": "gone 404: x"})
    _guard_record(env, "b", FALLBACK_MODEL, {"content": '{"verdict": "safe", "reason": "ok"}', "tool_calls": []},
                  fallback_for=FALLBACK_PRIMARY, started="2026-11-15T10:00:01+00:00")
    # A failed call in another turn, with no fallback, still shows as a block.
    _guard_record(env, "c", FALLBACK_PRIMARY, {"content": "", "tool_calls": [], "error": "gone 404: x"},
                  run_id="turn2", started="2026-11-15T10:01:00+00:00")
    rows = (await env.client.get("/api/guard/log")).json()
    assert [(r["model"], r["verdict"], r["fallback_for"]) for r in rows] == [
        (FALLBACK_PRIMARY, "error", None),
        (FALLBACK_MODEL, "safe", FALLBACK_PRIMARY),
    ]


async def test_settings_list_and_set_each_roles_fallback(make_env):
    env = make_env(admin=True)
    got = (await env.client.get("/api/settings/models")).json()
    assert got["fallbacks"] == {r: "anthropic/claude-haiku-5.5" for r in ("agent", "judge", "extractor", "guard")}
    r = await env.client.put("/api/settings/models/fallback", json={"role": "judge", "model": "google/gemini-3.8-flash"})
    assert r.status_code == 200 and r.json()["fallbacks"]["judge"] == "google/gemini-3.8-flash"
    r = await env.client.put("/api/settings/models/fallback", json={"role": "guard", "model": None})
    assert r.status_code == 200 and r.json()["fallbacks"]["guard"] is None
    for body in ({"role": "judge", "model": "evil/not-allowed"}, {"role": "nobody", "model": None}):
        assert (await env.client.put("/api/settings/models/fallback", json=body)).status_code == 422


async def test_only_the_admin_sets_a_fallback(make_env):
    env = make_env()
    r = await env.client.put("/api/settings/models/fallback", json={"role": "judge", "model": None})
    assert r.status_code == 403
    assert env.deps.model_settings.get_fallbacks()["judge"] == "anthropic/claude-haiku-5.5"
