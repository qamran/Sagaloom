"""The monthly AI budget (M5 spec §5.5a): a non-admin account over its budget gets 402 before a
new chat turn, a decision that resumes the graph, or an import; reading stays open, the admin is
never limited, and a turn already running finishes."""

from datetime import UTC, date, datetime
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda

from fakes import USER_A, W, create_call, names
from sagaloom.budget import budget_reset_date
from sagaloom.guard import GuardVerdict
from sagaloom.models import Entry
from sagaloom.promptlog import PromptRecord
from sagaloom.router import RouteDecision
from sagaloom.settings_store import DevSettingsPatch

NOW = datetime(2026, 11, 20, 9, 30, tzinfo=UTC)
OVER = "You've used this month's AI budget ($1.00). It resets on 2026-12-01."


def _spend(env, cost: float, at: str = "2026-11-02T10:00:00+00:00", id: str = "spent") -> None:
    env.deps.promptlog.add(
        PromptRecord(
            id=id, thread_id="t", run_id="r", provider="openrouter", model="m", role="agent",
            request={"messages": [], "tools": []},
            response={"prompt_tokens": 1, "completion_tokens": 1, "cost_usd": cost},
            started_at=at,
        ),
        user_id=USER_A,
    )


def _env(make_env, script=(), **kw):
    env = make_env(script, **kw)
    env.deps.now = lambda: NOW
    return env


async def _pending(env) -> str:
    """A thread in `W` holding a pending approval (one proposal)."""
    tid = await env.new_thread(W)
    r, events = await env.send(tid)
    assert r.status_code == 200 and names(events)[-1] == "done", names(events)
    assert (await env.client.get(f"/api/threads/{tid}")).json()["pending_interrupt"] is not None
    return tid


def test_budget_reset_date_is_the_first_of_next_month():
    assert budget_reset_date(NOW) == date(2026, 12, 1)
    assert budget_reset_date(datetime(2026, 12, 31, 23, 59, tzinfo=UTC)) == date(2027, 1, 1)


async def test_under_budget_allowed(make_env):
    env = _env(make_env, [AIMessage(content="Hello.")])
    _spend(env, 0.99)
    tid = await env.new_thread(W)
    r, events = await env.send(tid, "hi")
    assert r.status_code == 200 and names(events)[-1] == "done"


async def test_over_budget_402_on_message(make_env):
    env = _env(make_env, [AIMessage(content="Hello."), AIMessage(content="Not this one.")])
    tid = await env.new_thread(W)
    r, _ = await env.send(tid, "hi")
    assert r.status_code == 200
    summary = env.deps.threads.get(tid).summary
    assert summary is not None  # so "not cleared" below can fail
    _spend(env, 1.0)
    r, _ = await env.send(tid, "again")
    assert r.status_code == 402 and r.json() == {"detail": OVER}
    # Refused before the turn lock: no side effect on the thread, no model call.
    assert env.deps.threads.get(tid).summary == summary
    assert tid not in env.deps.locks
    assert len(env.agent.seen) == 1


def two_creates() -> AIMessage:
    """One agent message proposing two entries, so a decision batch can be mixed."""
    a, b = create_call("Ostra").tool_calls[0], create_call("Brask").tool_calls[0]
    return AIMessage(content="Drafting both.", tool_calls=[a, b])


async def test_over_budget_402_on_decisions(make_env):
    env = _env(make_env, [two_creates()])
    tid = await _pending(env)
    summary = env.deps.threads.get(tid).summary
    pending = (await env.client.get(f"/api/threads/{tid}")).json()["pending_interrupt"]
    p1, p2 = sorted(p["proposal_id"] for p in pending["proposals"])
    _spend(env, 1.0)
    # Any decision that is not a rejection is gated, alone or in a mixed batch.
    for actions in (("approve", "approve"), ("approve", "reject"), ("reject", "save_as_myth")):
        decisions = [{"proposal_id": p, "action": a} for p, a in zip((p1, p2), actions)]
        r, _ = await env.decide(tid, *decisions)
        assert r.status_code == 402 and r.json() == {"detail": OVER}, actions
    # Refused before the turn lock: the approval is still pending, nothing else changed.
    assert env.deps.threads.get(tid).summary == summary
    assert tid not in env.deps.locks
    assert (await env.client.get(f"/api/threads/{tid}")).json()["pending_interrupt"] == pending
    assert env.deps.store.list_entries(W) == []


async def _reject_all(env, tid: str):
    pending = (await env.client.get(f"/api/threads/{tid}")).json()["pending_interrupt"]
    return await env.decide(
        tid, *({"proposal_id": p["proposal_id"], "action": "reject"} for p in pending["proposals"])
    )


async def test_rejection_only_decisions_stay_available_over_budget(make_env):
    """Spec §5.5a: Review decisions that only reject stay available over budget. The commit
    records them, but the agent does not run (no unpaid model call): it reads the review notes
    on the next paid turn."""
    env = _env(make_env, [two_creates(), AIMessage(content="Noted, dropping both.")])
    tid = await _pending(env)
    calls, records = len(env.agent.seen), len(env.deps.promptlog.list(tid))
    _spend(env, 5.0)
    r, events = await _reject_all(env, tid)
    assert r.status_code == 200 and names(events)[-1] == "done", names(events)
    thread = (await env.client.get(f"/api/threads/{tid}")).json()
    assert thread["pending_interrupt"] is None
    assert env.deps.store.list_entries(W) == []
    row = next(t for t in (await env.client.get("/api/threads")).json() if t["thread_id"] == tid)
    assert (row["rejected"], row["approved"], row["pending"]) == (2, 0, 0)
    assert [m["role"] for m in thread["messages"]][-2:] == ["review", "review"]
    assert len(env.agent.seen) == calls  # no agent call
    assert len(env.deps.promptlog.list(tid)) == records  # and no prompt record


async def test_rejection_only_decisions_under_budget_tell_the_agent(make_env):
    env = _env(make_env, [two_creates(), AIMessage(content="Noted, dropping both.")])
    tid = await _pending(env)
    calls = len(env.agent.seen)
    r, events = await _reject_all(env, tid)
    assert r.status_code == 200 and names(events)[-1] == "done", names(events)
    assert len(env.agent.seen) == calls + 1
    messages = (await env.client.get(f"/api/threads/{tid}")).json()["messages"]
    assert messages[-1] == {**messages[-1], "role": "assistant", "content": "Noted, dropping both."}


async def test_over_budget_402_on_import(make_env):
    env = _env(make_env, real_extractor=True)
    _spend(env, 1.0)
    before = env.deps.threads.list(W)
    for body in (
        {"text": "Ostra is a deep-water port."},
        {"kind": "wiki", "urls": ["https://velmar.fandom.com/wiki/Ostra"]},
    ):
        r = await env.client.post(f"/api/worlds/{W}/imports", json=body)
        assert r.status_code == 402 and r.json() == {"detail": OVER}, body
    assert env.deps.threads.list(W) == before  # no import thread was made


async def test_402_detail_text(make_env):
    env = _env(make_env)
    _spend(env, 1.0, at="2026-11-20T08:00:00+00:00")
    tid = await env.new_thread(W)
    r, _ = await env.send(tid, "hi")
    assert r.status_code == 402
    assert r.json()["detail"] == "You've used this month's AI budget ($1.00). It resets on 2026-12-01."


async def test_402_detail_shows_the_configured_budget(make_env):
    env = _env(make_env)
    env.deps.dev_settings.update(DevSettingsPatch(monthly_budget_usd=2.5))
    _spend(env, 2.5)
    tid = await env.new_thread(W)
    r, _ = await env.send(tid, "hi")
    assert r.json()["detail"] == "You've used this month's AI budget ($2.50). It resets on 2026-12-01."


async def test_reads_still_work_over_budget(make_env):
    env = _env(make_env, [create_call()])
    env.deps.store.upsert_entry(Entry(id="ent_0001", world_id=W, title="Velmar", type="place", body="A city."))
    tid = await _pending(env)
    _spend(env, 5.0)
    for url in (
        f"/api/worlds/{W}/entries",
        f"/api/worlds/{W}/entries/ent_0001",
        f"/api/worlds/{W}/export",
        "/api/threads",
        f"/api/threads/{tid}",
        f"/api/threads/{tid}/llm-log",
        "/api/me",
    ):
        r = await env.client.get(url)
        assert r.status_code == 200, (url, r.text)
    assert (await env.client.post("/api/threads", json={"world_id": W})).status_code == 200


async def test_admin_never_blocked(make_env):
    env = _env(make_env, [AIMessage(content="Hello.")], admin=True)
    _spend(env, 50.0)
    tid = await env.new_thread(W)
    r, events = await env.send(tid, "hi")
    assert r.status_code == 200 and names(events)[-1] == "done"


async def test_turn_already_running_is_not_cut(make_env):
    env = None

    def script():
        # The spend crosses the line while the turn runs (the agent's call is under way).
        _spend(env, 1.0, id="mid-turn")
        yield AIMessage(content="Finishing this turn.")
        yield AIMessage(content="Never reached.")

    env = _env(make_env, script())
    tid = await env.new_thread(W)
    r, events = await env.send(tid, "hi")
    assert r.status_code == 200 and names(events)[-1] == "done", names(events)
    r, _ = await env.send(tid, "again")
    assert r.status_code == 402 and r.json() == {"detail": OVER}


async def test_previous_month_spend_ignored(make_env):
    env = _env(make_env, [AIMessage(content="Hello.")])
    _spend(env, 5.0, at="2026-10-31T23:59:59+00:00")
    tid = await env.new_thread(W)
    r, events = await env.send(tid, "hi")
    assert r.status_code == 200 and names(events)[-1] == "done"


async def test_budget_zero_blocks_everything_ai(make_env):
    env = _env(make_env, [create_call()])
    tid = await _pending(env)
    pid = await env.pending_id(tid)
    env.deps.dev_settings.update(DevSettingsPatch(monthly_budget_usd=0))
    zero = "You've used this month's AI budget ($0.00). It resets on 2026-12-01."
    other = await env.new_thread(W)
    responses = [
        (await env.send(other, "hi"))[0],
        (await env.decide(tid, {"proposal_id": pid, "action": "approve"}))[0],
        await env.client.post(f"/api/worlds/{W}/imports", json={"text": "Ostra is a port."}),
    ]
    assert [(r.status_code, r.json()["detail"]) for r in responses] == [(402, zero)] * 3


async def test_turn_records_use_the_app_clock(make_env):
    """One clock for spend (carry item 8): the prompt records of a turn are stamped with
    `deps.now`, the clock `month_spend` and the budget check read."""
    env = make_env([AIMessage(content="Hello.")])
    env.deps.now = lambda: datetime(2026, 10, 31, 23, 59, tzinfo=UTC)
    tid = await env.new_thread(W)
    r, _ = await env.send(tid, "hi")
    assert r.status_code == 200
    stamps = {rec.started_at for rec in env.deps.promptlog.list(tid)}
    assert stamps == {"2026-10-31T23:59:00+00:00"}
    nov = datetime(2026, 11, 1, tzinfo=UTC)
    assert env.deps.promptlog.month_spend(USER_A, nov) == 0
    assert env.deps.promptlog.month_spend(USER_A, env.deps.now()) > 0



class StructuredChat(BaseChatModel):
    """A structured-output role model that IS a chat model, so its call is prompt-logged."""

    reply: Any

    @property
    def _llm_type(self) -> str:
        return "structured-fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        msg = AIMessage(content="{}", usage_metadata={"input_tokens": 40, "output_tokens": 8, "total_tokens": 48})
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def with_structured_output(self, schema, **kwargs):
        return self | RunnableLambda(lambda _: self.reply)


async def test_guard_and_router_calls_are_the_users_spend(make_env):
    """Every model call of a turn is logged under the user, the guard's and router's too: an
    unlogged call would be spend the budget never sees."""
    env = make_env(
        [AIMessage(content="Hello.")],
        guard=StructuredChat(reply=GuardVerdict(verdict="safe", reason="ok"), metadata={"role": "guard"}),
        router=StructuredChat(reply=RouteDecision(mode="edit"), metadata={"role": "router"}),
    )
    tid = await env.new_thread(W)
    r, events = await env.send(tid, "hi")
    assert r.status_code == 200 and names(events)[-1] == "done"
    log = env.deps.promptlog
    assert len(log.list(tid)) == 3  # guard, router and the agent (whose fake has no role)
    for role in ("guard", "router"):
        assert len(log.list_by_role(role, 10, USER_A)) == 1, role
    assert log.usage(user_id=USER_A) == log.usage() and log.usage().cost_usd > 0
