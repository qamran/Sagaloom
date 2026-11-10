"""`import_wiki` (R-W3-6, R16.2): it proposes, never writes, and its result holds counts, titles and
reasons only, wrapped as untrusted data. No network: the cache is seeded from the committed
fixtures and synthetic pages come from `WikiServer`; the extractor is the shared stub."""

import json

import pytest
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from pydantic import ValidationError

from sagaloom.importing.extract import EXTRACTION_FAILED, PART_FAILED
from sagaloom.importing.wiki import LICENCE_UNREADABLE, PAGE_MISSING
from sagaloom.security import wrap_untrusted
from sagaloom.tools.wiki import ImportWikiArgs, make_import_wiki_tool
from wikifakes import FIXTURE_PAGES, LICENCE, WikiServer, page_extractor, parse_body, wiki_client

W = "w1"
URLS = [p["in"] for p in FIXTURE_PAGES]
TITLES = [p["title"] for p in FIXTURE_PAGES]  # Rivendell, Gandalf, The Shire
SENTINEL = "ZEBRA-7741"
QUILLON_URL = "https://en.wikipedia.org/wiki/Quillon"
QUILLON_LEAD = f"Quillon is a synthetic test town whose gate code is {SENTINEL}."
QUILLON = parse_body("Quillon", f"'''Quillon''' is a synthetic test town whose gate code is {SENTINEL}.")


class SpyStore:
    """The real store, recording every write call (there must be none)."""

    def __init__(self, store):
        self._store = store
        self.writes: list[str] = []

    def upsert_entry(self, *a, **kw):
        self.writes.append("upsert_entry")
        return self._store.upsert_entry(*a, **kw)

    def delete_entry(self, *a, **kw):
        self.writes.append("delete_entry")
        return self._store.delete_entry(*a, **kw)

    def __getattr__(self, name):
        return getattr(self._store, name)


@pytest.fixture
def wiki(tmp_path, aclose_later):
    """`wiki(server=None, seed=True)` -> (client, server); each client is closed at teardown."""
    count = 0

    def make(server: WikiServer | None = None, seed: bool = True):
        nonlocal count
        count += 1
        client, srv = wiki_client(tmp_path / f"cache{count}", server, seed)
        aclose_later(client)
        return client, srv

    return make


async def call(tool, urls, id="call_1") -> Command:
    return await tool.ainvoke(
        {"type": "tool_call", "name": "import_wiki", "id": id, "args": {"urls": urls, "world_id": W}}
    )


def message(cmd: Command) -> ToolMessage:
    [m] = cmd.update["messages"]
    return m


def payload(m: ToolMessage) -> dict:
    return json.loads(m.content.split("\n", 1)[1].rsplit("\n", 1)[0])


async def test_import_wiki_tool_returns_command_with_proposals(store, wiki):
    client, server = wiki()
    tool = make_import_wiki_tool(store, client, page_extractor())
    cmd = await call(tool, URLS)
    assert server.requests == []  # all from the seeded cache
    assert isinstance(cmd, Command)
    proposals = cmd.update["pending_proposals"]
    assert [p.after.title for p in proposals] == TITLES
    assert all(p.after.source == "official" and p.after.trusted is False for p in proposals)
    m = message(cmd)
    assert (m.tool_call_id, m.name, m.status) == ("call_1", "import_wiki", "success")
    result = payload(m)
    assert result["label"] == "import_wiki"
    assert result["proposals"] == 3
    assert result["pages"] == [{"title": t, "action": "create"} for t in TITLES]
    assert result["not_imported"] == []
    assert (result["licence"], result["nc"]) == (LICENCE["text"], False)
    assert "review" in result["note"]


async def test_import_wiki_tool_never_writes(store, wiki):
    spy = SpyStore(store)
    client, _ = wiki(WikiServer({"Nowhere": 404}))
    tool = make_import_wiki_tool(spy, client, page_extractor())
    await call(tool, [*URLS, "https://en.wikipedia.org/wiki/Nowhere"])
    assert spy.writes == []
    assert store.list_entries(W) == []


async def test_tool_result_has_titles_and_counts_only(store, wiki):
    client, _ = wiki(WikiServer({"Quillon": QUILLON, "Nowhere": 404}))
    tool = make_import_wiki_tool(store, client, page_extractor({"Quillon": QUILLON_LEAD}))
    cmd = await call(tool, [QUILLON_URL, "https://en.wikipedia.org/wiki/Nowhere"])
    [p] = cmd.update["pending_proposals"]
    assert SENTINEL in p.after.body  # the page text did come in, into the proposal only
    m = message(cmd)
    assert SENTINEL not in m.content
    assert m.content.startswith('<untrusted_data source="import_wiki">\n')
    assert m.content == wrap_untrusted(json.dumps(payload(m), ensure_ascii=False), "import_wiki")
    result = payload(m)
    assert set(result) == {"label", "proposals", "pages", "not_imported", "licence", "nc", "note"}
    assert result["pages"] == [{"title": "Quillon", "action": "create"}]
    assert result["not_imported"] == [{"title": "Nowhere", "reason": PAGE_MISSING}]


@pytest.mark.parametrize(
    "urls, copy",
    [
        (["not a url"], "Not a wiki page URL: not a url. Use a page link such as https://en.wikipedia.org/wiki/Gandalf."),
        (["https://example.com/wiki/Gandalf"], "Only Wikipedia and Fandom pages can be imported: https://example.com/wiki/Gandalf"),
        (
            ["https://en.wikipedia.org/wiki/Gandalf", "https://lotr.fandom.com/wiki/Gandalf"],
            "All URLs in one import must come from the same wiki.",
        ),
    ],
)
async def test_bad_urls_give_error_copy(store, wiki, urls, copy):
    client, server = wiki()
    tool = make_import_wiki_tool(store, client, page_extractor())
    cmd = await call(tool, urls)
    m = message(cmd)
    assert (m.status, m.content, m.tool_call_id, m.name) == ("error", copy, "call_1", "import_wiki")
    assert "pending_proposals" not in cmd.update
    assert server.requests == []


async def test_licence_failure_gives_error_copy(store, wiki):
    client, server = wiki(WikiServer({"Gandalf": parse_body("Gandalf", "Synthetic.")}, licence=403), seed=False)
    tool = make_import_wiki_tool(store, client, page_extractor())
    m = message(await call(tool, ["https://en.wikipedia.org/wiki/Gandalf"]))
    assert (m.status, m.content) == ("error", LICENCE_UNREADABLE.format(host="en.wikipedia.org"))
    assert server.parse_requests() == []


async def test_total_extraction_failure_gives_error_copy(store, wiki):
    client, _ = wiki()
    llm = page_extractor({t: RuntimeError("model down") for t in TITLES})
    cmd = await call(make_import_wiki_tool(store, client, llm), URLS)
    m = message(cmd)
    assert (m.status, m.content) == ("error", EXTRACTION_FAILED)
    assert "pending_proposals" not in cmd.update


async def test_partial_extraction_failure_still_proposes(store, wiki):
    client, _ = wiki()
    llm = page_extractor({"Gandalf": RuntimeError("model down")})
    m = message(cmd := await call(make_import_wiki_tool(store, client, llm), URLS))
    assert m.status == "success"
    assert len(cmd.update["pending_proposals"]) == 2
    assert payload(m)["not_imported"] == [{"title": "Gandalf", "reason": PART_FAILED}]


async def test_unexpected_error_is_named_by_type_and_the_agent_carries_on(store, wiki, monkeypatch):
    async def boom(*a, **kw):
        raise KeyError(f"secret page text {SENTINEL}")

    monkeypatch.setattr("sagaloom.tools.wiki.build_wiki_import", boom)
    client, _ = wiki()
    m = message(await call(make_import_wiki_tool(store, client, page_extractor()), URLS))
    assert (m.status, m.content) == ("error", "Could not import those pages: KeyError")


async def test_extractor_runs_under_the_turn_config(store, wiki):
    client, _ = wiki()
    llm = page_extractor()
    tool = make_import_wiki_tool(store, client, llm)
    await tool.ainvoke(
        {"type": "tool_call", "name": "import_wiki", "id": "c1", "args": {"urls": URLS[:1], "world_id": W}},
        {"metadata": {"turn": "t9"}},
    )
    [cfg] = llm.configs
    assert cfg["metadata"]["turn"] == "t9"


def test_schema_rejects_eleven_urls():
    urls = [f"https://en.wikipedia.org/wiki/Page_{i}" for i in range(11)]
    with pytest.raises(ValidationError):
        ImportWikiArgs(urls=urls, world_id=W, tool_call_id="c1")
    with pytest.raises(ValidationError):
        ImportWikiArgs(urls=[], world_id=W, tool_call_id="c1")
    assert len(ImportWikiArgs(urls=urls[:10], world_id=W, tool_call_id="c1").urls) == 10
    schema = make_import_wiki_tool(None, None, None).tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"urls"}  # world_id, call id and config are injected
