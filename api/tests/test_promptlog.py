"""Prompt capture (R20.1, R20.2, R12 cost)."""

import json
import uuid

import pytest
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, LLMResult

from sagaloom.config import Settings
from sagaloom.promptlog import PromptLog, PromptLogHandler
from sagaloom.security import wrap_untrusted

KEY = "sk-or-SECRET-KEY-123"
SHARED = "shared-SECRET-456"
S = Settings(_env_file=None, openrouter_api_key=KEY, api_shared_secret=SHARED)

TOOLS = [{"type": "function", "function": {"name": "search_canon", "parameters": {"type": "object"}}}]


def make_handler(tmp_path):
    log = PromptLog(tmp_path / "prompts.sqlite")
    events: list[tuple[str, dict]] = []
    handler = PromptLogHandler(
        log, "t1", lambda n, d: events.append((n, d)), settings=S, secrets=[KEY, SHARED]
    )
    return log, handler, events


async def start(handler, messages, params=None, run_id=None):
    run_id = run_id or uuid.uuid4()
    await handler.on_chat_model_start(
        {"name": "ChatOpenAI"},
        [messages],
        run_id=run_id,
        invocation_params={
            "model": "openai/gpt-6-luna",
            "temperature": 0.0,
            "max_tokens": 500,
            "tools": TOOLS,
            "api_key": KEY,
            "headers": {"Authorization": f"Bearer {KEY}"},
            **(params or {}),
        },
    )
    return run_id


def result(message, llm_output=None, generation_info=None):
    gen_cls = ChatGenerationChunk if isinstance(message, AIMessageChunk) else ChatGeneration
    return LLMResult(
        generations=[[gen_cls(message=message, generation_info=generation_info)]],
        llm_output=llm_output,
    )


async def test_handler_records_system_prompt_tools_and_wrapped_context(tmp_path):
    log, handler, events = make_handler(tmp_path)
    wrapped = wrap_untrusted("Ister is a river.", "search_canon")
    rid = await start(
        handler,
        [
            SystemMessage(content="You are the Sagaloom agent."),
            HumanMessage(content="Tell me about Ister"),
            AIMessage(
                content="",
                tool_calls=[{"name": "search_canon", "args": {"query": "Ister"}, "id": "c1", "type": "tool_call"}],
            ),
            ToolMessage(content=wrapped, tool_call_id="c1", name="search_canon"),
            HumanMessage(content="Review: p1 approved.", name="review"),
        ],
    )
    [rec] = log.list("t1")
    assert rec.id == str(rid) and rec.thread_id == "t1" and rec.response is None
    assert rec.model == "openai/gpt-6-luna"
    assert rec.params["temperature"] == 0.0 and rec.params["max_tokens"] == 500
    msgs = rec.request["messages"]
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "tool", "user"]
    assert msgs[0]["content"] == "You are the Sagaloom agent."
    assert msgs[2]["tool_calls"][0]["name"] == "search_canon"
    assert "<untrusted_data" in msgs[3]["content"] and msgs[3]["name"] == "search_canon"
    assert msgs[4]["name"] == "review"
    assert rec.request["tools"] == TOOLS
    assert events[0][0] == "llm_request"
    assert events[0][1]["messages"] == msgs and events[0][1]["tools"] == TOOLS


async def test_llm_request_event_carries_role_from_metadata(tmp_path):
    log, handler, events = make_handler(tmp_path)
    await handler.on_chat_model_start(
        {"name": "ChatOpenAI"},
        [[HumanMessage(content="hi")]],
        run_id=uuid.uuid4(),
        invocation_params={"model": "openai/gpt-6-luna"},
        metadata={"role": "judge"},
    )
    assert events[0][0] == "llm_request" and events[0][1]["role"] == "judge"
    assert log.list("t1")[0].role == "judge"


async def test_handler_redacts_api_key_everywhere(tmp_path):
    log, handler, events = make_handler(tmp_path)
    rid = await start(
        handler,
        [SystemMessage(content="sys"), HumanMessage(content=f"my key is {KEY} and {SHARED}")],
        params={"extra_body": {"authorization": "x", "openai_api_key": KEY, "note": KEY}},
    )
    await handler.on_llm_end(result(AIMessage(content=f"echo {KEY}")), run_id=rid)
    blob = json.dumps([r.model_dump() for r in log.list("t1")]) + json.dumps(events)
    assert KEY not in blob and SHARED not in blob
    for dropped in ("api_key", "openai_api_key", "authorization", "headers"):
        assert f'"{dropped}"' not in blob
    # the raw sqlite file never saw it either
    assert KEY.encode() not in (tmp_path / "prompts.sqlite").read_bytes()


async def test_handler_completes_response_and_emits(tmp_path):
    log, handler, events = make_handler(tmp_path)
    rid = await start(handler, [HumanMessage(content="hi")])
    msg = AIMessage(
        content="hello",
        tool_calls=[{"name": "search_canon", "args": {"query": "x"}, "id": "c1", "type": "tool_call"}],
        response_metadata={"token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.5}},
    )
    await handler.on_llm_end(result(msg), run_id=rid)
    [rec] = log.list("t1")
    r = rec.response
    assert r["content"] == "hello" and r["tool_calls"][0]["name"] == "search_canon"
    assert (r["prompt_tokens"], r["completion_tokens"], r["cost_usd"]) == (10, 5, 0.5)
    assert r["latency_ms"] >= 0
    assert [e[0] for e in events] == ["llm_request", "llm_response"]
    assert events[1][1]["cost_usd"] == 0.5


async def test_streamed_result_without_cost_falls_back_to_estimate(tmp_path):
    log, handler, _ = make_handler(tmp_path)
    rid = await start(handler, [HumanMessage(content="hi")])
    chunk = AIMessageChunk(
        content="hey", usage_metadata={"input_tokens": 1_000_000, "output_tokens": 1_000_000, "total_tokens": 2_000_000}
    )
    await handler.on_llm_end(result(chunk), run_id=rid)
    r = log.list("t1")[0].response
    assert r["prompt_tokens"] == 1_000_000
    assert r["cost_usd"] == pytest.approx(S.price_in_per_mtok + S.price_out_per_mtok)


@pytest.mark.parametrize("where", ["generation_info", "llm_output", "response_metadata"])
async def test_streamed_result_with_openrouter_cost_uses_real_cost(tmp_path, where):
    log, handler, _ = make_handler(tmp_path)
    rid = await start(handler, [HumanMessage(content="hi")])
    chunk = AIMessageChunk(
        content="hey",
        usage_metadata={"input_tokens": 1_000_000, "output_tokens": 1_000_000, "total_tokens": 2_000_000},
        response_metadata={"usage": {"cost": 0.0123}} if where == "response_metadata" else {},
    )
    res = result(
        chunk,
        llm_output={"token_usage": {"cost": 0.0123}} if where == "llm_output" else None,
        generation_info={"usage": {"cost": 0.0123}} if where == "generation_info" else None,
    )
    await handler.on_llm_end(res, run_id=rid)
    r = log.list("t1")[0].response
    assert r["cost_usd"] == 0.0123  # the real cost, not the 0.60 estimate
    assert r["prompt_tokens"] == 1_000_000


async def test_log_is_per_thread_and_survives_reopen(tmp_path):
    log, handler, _ = make_handler(tmp_path)
    await start(handler, [HumanMessage(content="hi")])
    assert [r.thread_id for r in PromptLog(tmp_path / "prompts.sqlite").list("t1")] == ["t1"]
    assert PromptLog(tmp_path / "prompts.sqlite").list("other") == []


def _rec(id, role, started_at, response=None, thread_id="t1"):
    from sagaloom.promptlog import PromptRecord

    return PromptRecord(
        id=id, thread_id=thread_id, run_id="r", provider="openrouter", model="m", role=role,
        request={"messages": [], "tools": []}, response=response, started_at=started_at,
    )


def test_list_by_role_returns_only_that_role_newest_first_capped(tmp_path):
    log = PromptLog(tmp_path / "prompts.sqlite")
    log.add(_rec("a", "guard", "2026-01-01T00:00:01"))
    log.add(_rec("b", "agent", "2026-01-01T00:00:02"))
    log.add(_rec("c", "guard", "2026-01-01T00:00:03", thread_id="t2"))
    log.add(_rec("d", "guard", "2026-01-01T00:00:04"))
    assert [r.id for r in log.list_by_role("guard")] == ["d", "c", "a"]
    assert [r.id for r in log.list_by_role("guard", limit=2)] == ["d", "c"]
    assert [r.id for r in log.list_by_role("agent")] == ["b"]
    assert log.list_by_role("judge") == []
