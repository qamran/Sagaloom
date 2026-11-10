"""POST /api/worlds/{id}/imports (R3.1, R3.2, R3.5, R13.6, R13.7, R18.10). No real LLM calls."""

import asyncio

from langchain_core.messages import AIMessage

from sagaloom.importing.extract import NOT_LOCATED, Candidate, ExtractionOutput
from sagaloom.models import Entry

from fakes import StubLLM, W, create_call, names, parse_sse
from wikifakes import FIXTURE_PAGES, LICENCE, WikiServer, wiki_client

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
        "a\u2028.md", "a\u2029.txt", "a\x85.md",
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
    assert note["import"]["kind"] == "text"
    assert note["import"]["skipped"] == [{"title": "Ghost Isle", "reason": NOT_LOCATED, "paste": False}]
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
            "kind": "text",
            "source": "notes.md",
            "first_lines": {ostra.proposal_id: OSTRA, market.proposal_id: gull},
            "skipped": [{"title": "Ghost Isle", "reason": NOT_LOCATED, "paste": False}],
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


# ---------- fan-wiki import (M3 Wave 3) ----------

EVENT_SET = {
    "token", "tool_call", "tool_result", "node", "llm_request", "llm_response", "interrupt", "usage", "done", "error",
}
FIXTURE_URLS = [p["in"] for p in FIXTURE_PAGES]
WIKI_LEADS = {
    "Gandalf": "He is a wizard, one of the Istari order, and the leader of the Company of the Ring.",
    "Rivendell": "It is an important location in The Hobbit and The Lord of the Rings, "
    "being the place where the quest to destroy the One Ring begins.",
    "The Shire": "The Shire is an inland area settled exclusively by hobbits, the Shire-folk, "
    "largely sheltered from the goings-on in the rest of Middle-earth.",
}


def lead_of_page(messages) -> ExtractionOutput:
    """The extractor's answer for one wiki page: its subject, quoting a lead sentence."""
    body = messages[-1].content
    start = body.index("Page title: ") + len("Page title: ")
    title = body[start : body.index("\n", start)]
    return found(Candidate(title=title, type="place", excerpt=WIKI_LEADS[title]))


def wiki_env(make_env, tmp_path, aclose_later, server: WikiServer | None = None, seed: bool = True):
    """An app whose wiki client reads a cache under `tmp_path` (seeded with the fixtures unless
    `seed` is False) and sends any request to `server`."""
    client, server = wiki_client(tmp_path / "wiki-cache", server, seed)
    aclose_later(client)
    return make_env(extraction=lead_of_page, wiki=client), server


async def post_wiki(env, urls: list[str], world_id: str = W):
    r = await env.client.post(f"/api/worlds/{world_id}/imports", json={"kind": "wiki", "urls": urls})
    return r, parse_sse(r.text) if r.status_code == 200 else []


async def test_wiki_import_streams_fetch_extract_check_and_returns_thread_id(make_env, tmp_path, aclose_later):
    env, server = wiki_env(make_env, tmp_path, aclose_later)
    r, events = await post_wiki(env, FIXTURE_URLS)
    assert r.status_code == 200
    assert server.requests == []  # the seeded cache served every page and the licence
    n = names(events)
    assert events[0] == ("node", {"name": "fetch", "phase": "start"})
    assert events[1] == (
        "tool_result", {"name": "fetch", "summary": "3 pages fetched, 0 not fetched", "pages": 3, "failed": 0}
    )
    assert events[2][0] == "node" and events[2][1]["name"] == "fetch" and events[2][1]["phase"] == "end"
    assert events[3] == ("node", {"name": "extract", "phase": "start"})
    assert n[4:10] == ["llm_request", "llm_response"] * 3
    assert events[10] == (
        "tool_result",
        {"name": "extract", "summary": "3 candidates, 0 not imported", "candidates": 3, "skipped": 0},
    )
    assert events[11][1]["name"] == "extract" and events[11][1]["phase"] == "end"
    assert events[12] == ("node", {"name": "check", "phase": "start"})
    assert set(n[12 : n.index("interrupt")]) == {"node"}
    assert n[-2:] == ["usage", "done"] and n.count("interrupt") == 1 and "error" not in n
    proposals = interrupt(events)["proposals"]
    assert [p["after"]["title"] for p in proposals] == [p["title"] for p in FIXTURE_PAGES]
    assert all(p["after"]["trusted"] is False and p["after"]["source"] == "official" for p in proposals)
    tid = events[-1][1]["thread_id"]
    [t] = import_threads(env)
    assert (t.thread_id, t.kind, t.title) == (tid, "import", "Fan wiki: en.wikipedia.org (3 pages)")
    assert tid not in env.deps.locks


async def test_wiki_import_uses_only_the_existing_event_set(make_env, tmp_path, aclose_later):
    env, _ = wiki_env(make_env, tmp_path, aclose_later)
    _, ok = await post_wiki(env, FIXTURE_URLS)
    env.deps.wiki, _ = wiki_client(tmp_path / "b", WikiServer(licence=403), seed=False)
    aclose_later(env.deps.wiki)
    _, licence_failure = await post_wiki(env, FIXTURE_URLS)
    env.deps.wiki, _ = wiki_client(tmp_path / "c", WikiServer({"Nowhere": 404}))
    aclose_later(env.deps.wiki)
    _, zero_pages = await post_wiki(env, ["https://en.wikipedia.org/wiki/Nowhere"])
    assert "interrupt" in names(ok) and "error" in names(licence_failure) and "done" in names(zero_pages)
    for stream in (ok, licence_failure, zero_pages):
        assert set(names(stream)) <= EVENT_SET


async def test_wiki_import_rejects_bad_urls_without_creating_a_thread(make_env, tmp_path, aclose_later):
    env, server = wiki_env(make_env, tmp_path, aclose_later)
    eleven = [f"https://en.wikipedia.org/wiki/Page_{i}" for i in range(11)]
    mixed = ["https://en.wikipedia.org/wiki/Gandalf", "https://lotr.fandom.com/wiki/Gandalf"]
    category = "https://en.wikipedia.org/wiki/Category:Middle-earth"
    elsewhere = "https://example.com/wiki/Gandalf"
    for urls, detail in [
        (eleven, "Paste 1 to 10 page URLs, one per line."),
        ([], "Paste 1 to 10 page URLs, one per line."),
        (mixed, "All URLs in one import must come from the same wiki."),
        ([category], f"Only article pages can be imported, not category, file or special pages: {category}"),
        ([elsewhere], f"Only Wikipedia and Fandom pages can be imported: {elsewhere}"),
    ]:
        r, _ = await post_wiki(env, urls)
        assert r.status_code == 422 and r.json() == {"detail": detail}, urls
    r, _ = await post_wiki(env, ["https://en.wikipedia.org/wiki/" + "x" * 2000])
    assert r.status_code == 422  # one URL over 2,000 characters
    assert env.deps.threads.list() == [] and server.requests == []


async def test_wiki_import_unknown_world_or_no_client(make_env, tmp_path, aclose_later):
    env, _ = wiki_env(make_env, tmp_path, aclose_later)
    r, _ = await post_wiki(env, FIXTURE_URLS, world_id="nope")
    assert r.status_code == 404
    env.deps.wiki = None
    r, _ = await post_wiki(env, FIXTURE_URLS)
    assert r.status_code == 503
    assert env.deps.threads.list() == []


async def test_wiki_import_licence_failure_is_error_and_removes_thread(make_env, tmp_path, aclose_later):
    env, server = wiki_env(make_env, tmp_path, aclose_later, WikiServer(licence=403), seed=False)
    r, events = await post_wiki(env, FIXTURE_URLS)
    assert r.status_code == 200
    assert names(events) == ["node", "node", "usage", "error"]
    assert [d["phase"] for e, d in events if e == "node"] == ["start", "end"]
    assert events[-1] == (
        "error",
        {
            "message": "Couldn't read the licence of en.wikipedia.org, so nothing was imported. "
            "A licence is never assumed: try again later, or paste the text instead.",
            "retryable": True,
        },
    )
    assert server.parse_requests() == []
    assert env.deps.threads.list() == []
    assert env.deps.store.list_entries(W) == []


async def test_wiki_import_with_no_fetched_pages_finishes_with_note(make_env, tmp_path, aclose_later):
    env, _ = wiki_env(make_env, tmp_path, aclose_later, WikiServer({"Nowhere": 404, "Elsewhere": 429}))
    urls = ["https://en.wikipedia.org/wiki/Nowhere", "https://en.wikipedia.org/wiki/Elsewhere"]
    _, events = await post_wiki(env, urls)
    n = names(events)
    assert "interrupt" not in n and "llm_request" not in n and n[-2:] == ["usage", "done"]
    assert [d["name"] for e, d in events if e == "node"][:2] == ["fetch", "fetch"]
    assert "extract" not in [d.get("name") for _, d in events]
    tid = events[-1][1]["thread_id"]
    body = (await env.client.get(f"/api/threads/{tid}")).json()
    [note] = body["messages"]
    assert note["content"] == "Imported wiki pages: 0 proposals for review, 2 not imported."
    assert note["import"]["skipped"] == [
        {"title": "Nowhere", "reason": "the page does not exist", "paste": True},
        {"title": "Elsewhere", "reason": "the wiki asked us to slow down (HTTP 429)", "paste": True},
    ]
    assert body["pending_interrupt"] is None


async def test_wiki_note_is_neutral(make_env, tmp_path, aclose_later):
    env, _ = wiki_env(make_env, tmp_path, aclose_later)
    _, events = await post_wiki(env, FIXTURE_URLS)
    tid = events[-1][1]["thread_id"]
    body = (await env.client.get(f"/api/threads/{tid}")).json()
    [note] = body["messages"]
    assert note["role"] == "import"
    assert note["content"] == "Imported wiki pages: 3 proposals for review, 0 not imported."
    for page in FIXTURE_PAGES:
        assert page["title"] not in note["content"]
    for lead in WIKI_LEADS.values():
        assert lead[:20] not in note["content"]
    payload = note["import"]
    assert (payload["kind"], payload["source"], payload["skipped"]) == ("wiki", "en.wikipedia.org", [])
    assert payload["licence"] == {"text": LICENCE["text"], "url": LICENCE["url"], "nc": False}
    pids = [p["proposal_id"] for p in body["pending_interrupt"]["proposals"]]
    assert list(payload["first_lines"]) == pids


async def test_text_import_body_still_accepted_without_kind(make_env):
    env = make_env(extraction=found(cand("Ostra", OSTRA)))
    r = await env.client.post(f"/api/worlds/{W}/imports", json={"text": OSTRA, "filename": "notes.md"})
    assert r.status_code == 200 and names(parse_sse(r.text))[-1] == "done"
    r = await env.client.post(f"/api/worlds/{W}/imports", json={"kind": "text", "text": OSTRA})
    assert r.status_code == 200 and names(parse_sse(r.text))[-1] == "done"


async def test_wiki_import_of_pages_without_text_finishes_with_note(make_env, tmp_path, aclose_later):
    """Fetched pages that all have no article text run no extraction call, and still end with the
    note, not the extraction-failed error."""
    server = WikiServer({"Mercury": {"parse": {"title": "Mercury", "wikitext": "{{Disambiguation}}"}}})
    env, _ = wiki_env(make_env, tmp_path, aclose_later, server)
    _, events = await post_wiki(env, ["https://en.wikipedia.org/wiki/Mercury"])
    n = names(events)
    assert "error" not in n and "llm_request" not in n and n[-2:] == ["usage", "done"]
    body = (await env.client.get(f"/api/threads/{events[-1][1]['thread_id']}")).json()
    assert body["messages"][0]["import"]["skipped"] == [
        {"title": "Mercury", "reason": "the page has no article text", "paste": False}
    ]
