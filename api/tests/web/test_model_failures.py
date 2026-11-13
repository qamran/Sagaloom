"""A failed model call says which step and model failed, why, and what to do (model_errors), at
every place an author meets it: the Chat error, the guard's notice, the approval card's check
line, the import error, Under the hood and Studio → Guardrails."""

import itertools

import httpx
import openai
from fakes import USER_A, W, create_call, endless, names

from sagaloom.models import Entry
from sagaloom.promptlog import PromptRecord

URL = "https://openrouter.ai/api/v1/chat/completions"


def api_error(cls, status: int, message: str, model: str = "openai/gpt-x"):
    request = httpx.Request("POST", URL, json={"model": model})
    return cls(message, response=httpx.Response(status, request=request),
               body={"error": {"message": message, "code": status}})


def gone():
    return api_error(openai.NotFoundError, 404, "No endpoints found for openai/gpt-x.")


async def test_chat_names_a_removed_model_and_offers_no_retry(make_env):
    env = make_env([gone()])
    tid = await env.new_thread()
    _, events = await env.send(tid)
    [err] = [d for e, d in events if e == "error"]
    assert err["message"] == (
        "The chat model (openai/gpt-x) is no longer available on OpenRouter from its provider, so I "
        "couldn't reply. An admin can choose another model in Studio → Models and providers."
    )
    assert err["retryable"] is False  # trying again cannot help
    assert "done" not in names(events)
    # Under the hood keeps the cause on the failed call's record.
    [rec] = [r for r in env.deps.promptlog.list(tid) if r.role is None or r.role == "agent"][-1:]
    assert rec.response["error"].startswith("gone 404: No endpoints found")
    assert rec.response["cost_usd"] == 0.0


async def test_chat_out_of_credit(make_env):
    env = make_env([api_error(openai.APIStatusError, 402, "Insufficient credits")])
    tid = await env.new_thread()
    _, events = await env.send(tid)
    [err] = [d for e, d in events if e == "error"]
    assert err == {
        "message": "The OpenRouter account is out of credit, so I couldn't reply. "
        "Add credit at openrouter.ai, then try again.",
        "retryable": False,
    }


async def test_guard_notice_names_its_model_and_where_to_change_it(make_env):
    from stubs import StubLLM

    env = make_env(endless(lambda: create_call()), guard=StubLLM(gone()))
    tid = await env.new_thread()
    r, events = await env.send(tid)
    text = "".join(d.get("text", "") for e, d in events if e == "token")
    assert text.startswith("The input guard's model (openai/gpt-x) is no longer available on OpenRouter")
    assert "so I couldn't check your message and didn't act on it" in text
    assert "GUARD_MODEL in api/.env" in text


async def test_check_line_says_the_judge_model_was_refused(make_env):
    env = make_env(
        itertools.chain([create_call()], endless(lambda: create_call())),
        judge_reply=api_error(openai.PermissionDeniedError, 403, "Model not allowed by guardrail"),
    )
    # A related entry, so the judge is called (an empty world has nothing to check against).
    env.deps.store.upsert_entry(Entry(id="ent_0001", world_id=W, title="Harbour Ward", type="place", body="The docks of Ostra."))
    tid = await env.new_thread()
    r, events = await env.send(tid)
    assert "interrupt" in names(events)
    body = (await env.client.get(f"/api/threads/{tid}")).json()
    checks = body["pending_interrupt"]["checks"]
    [result] = checks.values() if isinstance(checks, dict) else checks
    assert result["verdict"] == "failed"
    [note] = [f for f in result["flags"] if f["kind"] == "note"]
    assert note["explanation"].startswith(
        "OpenRouter refused the contradiction judge's model (openai/gpt-x): this API key is not allowed to use it"
    )
    assert "so the contradiction check could not run" in note["explanation"]


async def test_import_error_names_the_extractor_failure(make_env):
    from test_imports import OSTRA, post_import

    env = make_env(extraction=api_error(openai.APIStatusError, 402, "Insufficient credits"))
    _, events = await post_import(env, OSTRA)
    assert events[-1] == ("error", {
        "message": "The OpenRouter account is out of credit, so nothing was imported. "
        "Add credit at openrouter.ai, then try again.",
        "retryable": False,
    })


async def test_guard_log_shows_the_cause_of_a_failed_call(make_env):
    env = make_env()
    tid = env.deps.threads.create(W)
    env.deps.promptlog.add(
        PromptRecord(
            id="g1", thread_id=tid, run_id="r", provider="openrouter", model="google/gemma", role="guard",
            request={"messages": [], "tools": []}, started_at="2026-01-01T00:00:01",
            response={"content": "", "tool_calls": [], "error": "gone 404: No endpoints found"},
        ),
        user_id=USER_A,
    )
    [row] = (await env.client.get("/api/guard/log")).json()
    assert (row["verdict"], row["reason"]) == ("error", "gone 404: No endpoints found")
