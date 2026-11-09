"""POST /api/worlds/{id}/imports (R3.1, R3.2, R3.5, R13.6, R13.7, R18.10). No real LLM calls."""

import asyncio

from langchain_core.messages import AIMessage

from sagaloom.importing.extract import NOT_LOCATED, Candidate, ExtractionOutput
from sagaloom.models import Entry

from fakes import W, create_call, names, parse_sse

OSTRA = "Ostra is a port town with a deep harbour."
EXTRACTION_FAILED = "The extraction could not run, so nothing was imported. Try again."


def cand(title: str, excerpt: str) -> Candidate:
    return Candidate(title=title, type="place", excerpt=excerpt, facts=[{"key": "Harbour", "value": "Deep"}])


def found(*cands: Candidate) -> ExtractionOutput:
    return ExtractionOutput(candidates=list(cands))


async def post_import(env, text: str, filename: str | None = "session-12-notes.md", world_id: str = W):
    body = {"text": text} if filename is None else {"text": text, "filename": filename}
    r = await env.client.post(f"/api/worlds/{world_id}/imports", json=body)
    return r, parse_sse(r.text) if r.status_code == 200 else []


class StubLLM:
    """An extractor stub: `reply` is an ExtractionOutput to return, or an exception to raise. With
    `include_raw=True` it answers as LangChain does: {"raw", "parsed", "parsing_error"}."""

    def __init__(self, reply) -> None:
        self.reply = reply
        self.include_raw = False

    def with_structured_output(self, schema, **kwargs):
        self.include_raw = kwargs.get("include_raw", False)
        return self

    async def ainvoke(self, messages, config=None):
        if isinstance(self.reply, Exception):
            raise self.reply
        if not self.include_raw:
            return self.reply
        return {"raw": AIMessage(content=self.reply.model_dump_json()), "parsed": self.reply, "parsing_error": None}


def interrupt(events) -> dict:
    return next(d for e, d in events if e == "interrupt")


def import_threads(env) -> list:
    return env.deps.threads.list(W, "import")


async def test_import_streams_extraction_then_check_and_returns_thread_id(make_env):
    env = make_env(extraction=found(cand("Ostra", OSTRA)))
    r, events = await post_import(env, "Notes.\n\n" + OSTRA)
    assert r.status_code == 200
    n = names(events)
    assert events[0] == ("node", {"name": "extract", "phase": "start"})
    assert n[1:3] == ["llm_request", "llm_response"]
    assert events[1][1]["role"] == "extractor"
    assert events[3] == (
        "tool_result",
        {"name": "extract", "summary": "1 candidates, 0 not imported", "candidates": 1, "skipped": 0},
    )
    assert events[4][0] == "node" and events[4][1]["name"] == "extract" and events[4][1]["phase"] == "end"
    assert events[5] == ("node", {"name": "check", "phase": "start"})
    # The graph's node events (the gate's end can trail its interrupt), then usage and done.
    assert n[-2:] == ["usage", "done"] and n.count("interrupt") == 1
    assert set(n[5 : n.index("interrupt")]) == {"node"}
    assert "error" not in n
    [proposal] = interrupt(events)["proposals"]
    assert proposal["after"]["body"] == OSTRA
    assert proposal["after"]["trusted"] is False and proposal["after"]["source"] == "user"
    usage = events[-2][1]
    assert usage["turn"]["prompt_tokens"] == 30  # the extractor's call counts in the turn
    tid = events[-1][1]["thread_id"]
    [t] = import_threads(env)
    assert (t.thread_id, t.kind, t.title) == (tid, "import", "session-12-notes.md")
    log = (await env.client.get(f"/api/threads/{tid}/llm-log")).json()
    assert [rec["role"] for rec in log] == ["extractor"]
    # The lock is released once the run ends.
    assert tid not in env.deps.locks  # released and pruned


async def test_paste_title_uses_first_line(make_env):
    env = make_env(extraction=found())
    first = "  The long first line of my notes about the harbour town of Ostra and its people"
    r, events = await post_import(env, "\n  \n" + first + "\nmore", filename=None)
    assert r.status_code == 200 and names(events)[-1] == "done"
    [t] = import_threads(env)
    assert t.title == "Pasted text: " + first.strip()[:60]


async def test_paste_label_is_paste(make_env, store):
    store.upsert_entry(Entry(id="ent_0001", world_id=W, title="Ostra", type="place", body="A port."))
    env = make_env(extraction=found(cand("Ostra", OSTRA)))
    _, events = await post_import(env, OSTRA, filename=None)
    [proposal] = interrupt(events)["proposals"]
    assert "\n\n## Imported from paste (" in proposal["after"]["body"]


async def test_import_rejects_blank_text_without_creating_a_thread(make_env):
    env = make_env(extraction=found())
    r, _ = await post_import(env, "  \n\t \n")
    assert r.status_code == 422 and r.json() == {"detail": "Paste or upload some text first."}
    r, _ = await post_import(env, "")
    assert r.status_code == 422
    assert env.deps.threads.list() == []


async def test_import_rejects_bad_filename(make_env):
    env = make_env(extraction=found())
    for bad in [
        "notes.pdf", "../a.md", "a\\b.txt", "x" * 118 + ".md", "a\n.md", "a\x01b.txt", "a\x7f.md",
        "a .md", "a .txt", "a\x85.md",
    ]:
        r, _ = await post_import(env, OSTRA, filename=bad)
        assert r.status_code == 422, bad
    r, _ = await post_import(env, OSTRA, filename="Notes.MD")
    assert r.status_code == 200
    assert env.deps.threads.list()[0].title == "Notes.MD"


async def test_import_unknown_world_404(make_env):
    env = make_env(extraction=found())
    r, _ = await post_import(env, OSTRA, world_id="nope")
    assert r.status_code == 404
    assert env.deps.threads.list() == []


async def test_import_rejects_over_100k(make_env):
    env = make_env(extraction=found())
    r, _ = await post_import(env, "x" * 100_001)
    assert r.status_code == 422
    assert env.deps.threads.list() == []


async def test_import_note_is_in_thread_and_neutral(make_env):
    env = make_env(extraction=found(cand("Ostra", OSTRA), cand("Ghost Isle", "A line the text never had.")))
    _, events = await post_import(env, OSTRA)
    tid = events[-1][1]["thread_id"]
    body = (await env.client.get(f"/api/threads/{tid}")).json()
    [note] = body["messages"]
    assert note["role"] == "import"
    assert note["content"] == "Imported text: 1 proposals for review, 1 not imported."
    assert note["import"]["source"] == "session-12-notes.md"
    assert note["import"]["skipped"] == [{"title": "Ghost Isle", "reason": NOT_LOCATED}]
    [pid] = note["import"]["first_lines"]
    assert note["import"]["first_lines"][pid] == OSTRA
    for leaked in ("Ostra", "Ghost Isle", "harbour"):
        assert leaked not in note["content"]
    assert body["pending_interrupt"]["proposals"][0]["proposal_id"] == pid


async def test_import_with_no_located_candidates_finishes_with_note(make_env):
    env = make_env(extraction=found(cand("Ghost Isle", "Never said."), cand("Mist Tower", "Not here either.")))
    _, events = await post_import(env, OSTRA)
    n = names(events)
    assert "interrupt" not in n and n[-2:] == ["usage", "done"]
    tid = events[-1][1]["thread_id"]
    [row] = (await env.client.get("/api/threads", params={"world_id": W})).json()
    assert row["thread_id"] == tid and row["pending"] == 0 and row["kind"] == "import"
    body = (await env.client.get(f"/api/threads/{tid}")).json()
    [note] = body["messages"]
    assert note["content"] == "Imported text: 0 proposals for review, 2 not imported."
    assert [s["title"] for s in note["import"]["skipped"]] == ["Ghost Isle", "Mist Tower"]
    assert body["pending_interrupt"] is None


async def test_total_extraction_failure_is_error_and_removes_thread(make_env):
    env = make_env(extraction=RuntimeError("model down"))
    r, events = await post_import(env, OSTRA)
    assert r.status_code == 200
    assert events[-1] == ("error", {"message": EXTRACTION_FAILED, "retryable": True})
    assert "done" not in names(events) and "node" in names(events)
    assert [e for e, d in events if e == "node" and d["name"] != "extract"] == []  # graph never ran
    assert env.deps.threads.list() == []
    assert env.deps.store.list_entries(W) == []


async def test_total_extraction_failure_reports_usage_then_error(make_env):
    """The extractor's spend is reported even though nothing was imported (M12): `usage`, then
    `error`, and no `done`."""
    from sagaloom.graph.build import run_config
    from sagaloom.models import Usage
    from sagaloom.web.imports import import_events

    env = make_env(extraction=found())
    tid = env.deps.threads.create(W, kind="import", title="notes.md")
    turn, total = Usage(prompt_tokens=7, completion_tokens=2), Usage(prompt_tokens=90)
    events = [
        ev
        async for ev in import_events(
            env.deps.graph, env.deps.store, StubLLM(RuntimeError("model down")), W, tid, OSTRA,
            "notes.md", run_config(tid, W), asyncio.Queue(), lambda: (turn, total), env.deps.threads,
        )
    ]
    n = [ev["event"] for ev in events]
    assert n[-4:] == ["tool_result", "node", "usage", "error"]
    assert "done" not in n
    assert events[-2]["data"] == {"turn": turn.model_dump(), "total": total.model_dump()}
    assert events[-1]["data"] == {"message": EXTRACTION_FAILED, "retryable": True}
    assert env.deps.threads.get(tid) is None


async def test_import_closes_extraction_stream_when_closed(make_env, monkeypatch):
    """`import_events` closes the `_extraction` stream it iterates as soon as it is closed itself,
    not whenever the event loop's async-generator finaliser gets round to it (M12)."""
    from sagaloom.graph.build import run_config
    from sagaloom.models import Usage
    from sagaloom.web import imports

    sentinel = {"event": "node", "data": {"name": "sentinel", "phase": "start"}}
    closed = False

    async def fake_extraction(job, queue):
        nonlocal closed
        try:
            yield sentinel
            await asyncio.Event().wait()
        finally:
            closed = True

    monkeypatch.setattr(imports, "_extraction", fake_extraction)
    env = make_env(extraction=found())
    tid = env.deps.threads.create(W, kind="import", title="notes.md")
    gen = imports.import_events(
        env.deps.graph, env.deps.store, BlockingExtractor(), W, tid, OSTRA, "notes.md",
        run_config(tid, W), asyncio.Queue(), lambda: (Usage(), Usage()), env.deps.threads,
    )
    async for ev in gen:  # `node start` comes first, before `_extraction` is entered
        if ev == sentinel:
            break
    await gen.aclose()
    assert closed


async def test_import_note_payload_is_exact(store):
    """The whole note payload, not one key of it (Wave 5 M13)."""
    from sagaloom.importing.extract import build_import
    from sagaloom.web.imports import import_note

    gull = "Gull Market sells fish at dawn."
    text = OSTRA + "\n\n" + gull
    llm = StubLLM(found(cand("Ostra", OSTRA), cand("Gull Market", gull), cand("Ghost Isle", "Never said.")))
    plan = await build_import(store, llm, W, text, "notes.md")
    ostra, market = plan.proposals
    note = import_note(plan, "notes.md")
    assert note.content == "Imported text: 2 proposals for review, 1 not imported."
    assert note.additional_kwargs == {
        "import": {
            "source": "notes.md",
            "first_lines": {ostra.proposal_id: OSTRA, market.proposal_id: gull},
            "skipped": [{"title": "Ghost Isle", "reason": NOT_LOCATED}],
        }
    }


async def test_import_while_chat_pending_is_not_blocked(make_env):
    env = make_env([create_call(), AIMessage(content="Saved.")], extraction=found(cand("Ostra", OSTRA)))
    chat = await env.new_thread()
    await env.send(chat)
    assert (await env.client.get(f"/api/threads/{chat}")).json()["pending_interrupt"] is not None
    r, events = await post_import(env, OSTRA)
    assert r.status_code == 200 and names(events)[-1] == "done"
    assert events[-1][1]["thread_id"] != chat


class BlockingExtractor:
    """An extractor whose call waits until the test lets it go (or the task is cancelled)."""

    def __init__(self) -> None:
        self.started = asyncio.Event()

    def with_structured_output(self, schema, **kwargs):
        return self

    async def ainvoke(self, messages, config=None):
        self.started.set()
        await asyncio.Event().wait()


async def test_shutdown_during_extraction_removes_the_import_row(make_env):
    """R-W5-5 extended (M6): a shutdown that cancels the run before any plan exists leaves no
    empty import row behind, and the turn lock is released."""
    from sagaloom.graph.build import run_config
    from sagaloom.models import Usage
    from sagaloom.web.app import _cancel_turns
    from sagaloom.web.imports import import_events
    from sagaloom.web.sse import shielded

    env = make_env(extraction=found())
    tid = env.deps.threads.create(W, kind="import", title="notes.md")
    lock = env.deps.locks.setdefault(tid, asyncio.Lock())
    await lock.acquire()
    extractor = BlockingExtractor()
    events = import_events(
        env.deps.graph, env.deps.store, extractor, W, tid, OSTRA, "notes.md",
        run_config(tid, W), asyncio.Queue(), lambda: (Usage(), Usage()), env.deps.threads,
    )
    gen = shielded(events, on_finish=lock.release, tasks=env.deps.tasks)
    assert (await gen.__anext__()) == {"event": "node", "data": {"name": "extract", "phase": "start"}}
    await asyncio.wait_for(extractor.started.wait(), 5)
    await asyncio.wait_for(_cancel_turns(env.deps.tasks), 5)
    assert import_threads(env) == []
    assert not lock.locked() and env.deps.tasks == set()


async def test_import_writes_the_thread_summary(make_env):
    """#73: the import's summary is in the registry when the stream ends, so the list reads none."""
    env = make_env(extraction=found(cand("Ostra", OSTRA)))
    r, events = await post_import(env, "Notes.\n\n" + OSTRA)
    assert names(events)[-1] == "done"
    [t] = import_threads(env)
    assert t.summary is not None
    assert (t.summary.pending, t.summary.title) == (1, "session-12-notes.md")
