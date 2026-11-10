"""The fan-wiki import core (R-W3-1..R-W3-5, R13.6, R13.7). No network: HTTP goes through
`httpx.MockTransport` and a cache seeded from the committed Wikipedia fixtures; the model is a
stub; synthetic pages are synthetic text, never Fandom content."""

import json
from datetime import date

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from sagaloom.check.myth import apply_save_as_myth
from sagaloom.importing.extract import (
    INVALID,
    NOT_LOCATED,
    PART_FAILED,
    TRUNCATED,
    Candidate,
    CandidateFact,
    ExtractionOutput,
    Skipped,
)
from sagaloom.importing.wiki import (
    BLOCKED,
    NO_TEXT,
    NOT_REQUESTED,
    PAGE_MISSING,
    RATE_LIMITED,
    SAME_PAGE,
    UNREACHABLE,
    WIKI_EXTRACT_SYSTEM,
    build_wiki_import,
    extraction_text,
    fetch_wiki,
)
from sagaloom.importing.wikitext import strip_wikitext
from sagaloom.models import CheckResult, Entry, EntrySource, Fact
from sagaloom.provenance import is_import_merge, provenance_fields
from sagaloom.wiki.client import LicenceUnreadable
from sagaloom.wiki.pages import parse_page_urls
from stubs import StubLLM
from wikifakes import FIXTURE_PAGES, FIXTURES, LEAD, LICENCE, WikiServer, api_error, parse_body, rightsinfo_body, wiki_client

W = "w1"
TODAY = date(2026, 11, 9)
URLS = [p["in"] for p in FIXTURE_PAGES]
TITLES = [p["title"] for p in FIXTURE_PAGES]  # Rivendell, Gandalf, The Shire
URL_OF = {p["title"]: p["url"] for p in FIXTURE_PAGES}


ELROND = "https://en.wikipedia.org/wiki/Elrond_(character)"
ELROND_TEXT = (
    "'''Elrond''' is a synthetic test character who keeps a house in a quiet valley.\n\n"
    "== Later ==\nHe sails away at the end of the story."
)


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


def cand(title, excerpt, type="item", aliases=(), facts=()) -> Candidate:
    return Candidate(
        title=title,
        type=type,
        aliases=list(aliases),
        facts=[CandidateFact(key=k, value=v) for k, v in facts],
        excerpt=excerpt,
    )


def page_title_of(messages) -> str:
    """The `Page title:` label of an extraction prompt."""
    body = messages[-1].content
    start = body.index("Page title: ") + len("Page title: ")
    return body[start : body.index("\n", start)]


def by_page(replies: dict | None = None) -> StubLLM:
    """A stub that answers each page by its title: a Candidate, a list of them, or an exception.
    A page it has no answer for gets a candidate quoting its lead sentence."""
    replies = replies or {}

    def reply(messages):
        title = page_title_of(messages)
        found = replies.get(title)
        if isinstance(found, Exception):
            return found
        if found is None:
            found = cand(title, LEAD[title])
        return ExtractionOutput(candidates=found if isinstance(found, list) else [found])

    return StubLLM(reply)


def fixture_text(title: str) -> str:
    """The stripped text of a committed fixture page."""
    for f in FIXTURES.glob("*.v2.json"):
        parse = json.loads(f.read_text(encoding="utf-8"))["body"].get("parse")
        if parse and parse["title"] == title:
            return parse["wikitext"]
    raise KeyError(title)


async def fixture_plan(store, wiki, llm=None, urls=URLS):
    client, server = wiki()
    fetched = await fetch_wiki(client, parse_page_urls(urls))
    plan = await build_wiki_import(store, llm or by_page(), W, fetched, today=TODAY)
    return plan, fetched, server


def seed(store, title, body, facts=(), sources=(), id="ent_0001") -> Entry:
    return store.upsert_entry(
        Entry(
            id=id, world_id=W, title=title, type="place", body=body, facts=list(facts),
            **provenance_fields(list(sources), trusted=False),
        )
    )


# ---------- creates on the fixtures ----------


async def test_three_pages_give_three_official_untrusted_creates(store, wiki):
    plan, fetched, server = await fixture_plan(store, wiki)
    assert server.requests == []  # all three pages and the licence come from the seeded cache
    assert [p.action for p in plan.proposals] == ["create"] * 3
    assert [p.after.title for p in plan.proposals] == TITLES
    for p in plan.proposals:
        assert p.after.source == "official" and p.after.trusted is False
        assert p.after.licence == LICENCE["text"]
        assert p.after.source_url == URL_OF[p.after.title]
        [src] = p.after.sources
        assert src.kind == "official" and src.url == URL_OF[p.after.title]
        assert (src.licence, src.licence_url, src.nc) == (LICENCE["text"], LICENCE["url"], False)
    types = {p.after.title: p.after.type for p in plan.proposals}
    assert types["Gandalf"] == "character"  # from the infobox, over the stub's "item"
    assert types["Rivendell"] == "place"
    assert plan.licence == {"text": LICENCE["text"], "url": LICENCE["url"], "nc": False}
    assert (plan.parts, plan.failed_parts, plan.skipped) == (3, 0, [])
    assert plan.first_lines == {p.proposal_id: LEAD[p.after.title][:120] for p in plan.proposals}
    assert (fetched.host, fetched.lang_path, fetched.requested) == ("en.wikipedia.org", "", 3)


async def test_wiki_body_is_verbatim_slice_of_stripped_text(store, wiki):
    spaced = {t: "  " + LEAD[t].replace(" ", "\n   ", 3) + " " for t in LEAD}  # whitespace only
    llm = by_page({t: cand(t, spaced[t]) for t in LEAD})
    plan, _, _ = await fixture_plan(store, wiki, llm)
    assert len(plan.proposals) == 3
    for p in plan.proposals:
        body = p.after.body.removesuffix("\n\n" + TRUNCATED)
        assert body == LEAD[p.after.title]
        assert body in strip_wikitext(fixture_text(p.after.title)).text

    llm = by_page({"Gandalf": cand("Gandalf", "Page title: Gandalf\n\n" + LEAD["Gandalf"])})
    plan, _, _ = await fixture_plan(store, wiki, llm)
    assert [s.model_dump() for s in plan.skipped] == [{"title": "Gandalf", "reason": NOT_LOCATED, "paste": False}]
    assert sorted(p.after.title for p in plan.proposals) == ["Rivendell", "The Shire"]


async def test_wiki_extraction_has_no_tools_bound(store, wiki):
    llm = by_page()
    cfg = {"callbacks": [], "metadata": {"x": 1}}
    client, _ = wiki()
    fetched = await fetch_wiki(client, parse_page_urls(URLS))
    await build_wiki_import(store, llm, W, fetched, config=cfg, today=TODAY)
    assert llm.schemas == [ExtractionOutput] * 3  # bind_tools would have raised
    assert llm.kwargs == [{"include_raw": True}] * 3
    assert llm.configs == [cfg] * 3


async def test_wiki_text_is_wrapped_with_page_label(store, wiki):
    llm = by_page()
    await fixture_plan(store, wiki, llm, urls=[URLS[1]])
    [[system, human]] = llm.prompts
    assert isinstance(system, SystemMessage) and isinstance(human, HumanMessage)
    assert system.content == WIKI_EXTRACT_SYSTEM
    for page_text in ("Gandalf", "Istari", "Page title: Gandalf"):
        assert page_text not in system.content
    assert human.content.count('<untrusted_data source="import:wiki:en.wikipedia.org/Gandalf">') == 1
    assert human.content.count("<untrusted_data") == 1
    assert human.content.count("</untrusted_data>") == 1
    assert "\nPage title: Gandalf\n\n" in human.content


async def test_extraction_text_is_lead_only(store, wiki):
    """Open question 2 (a): the lead section, infobox lines included; one call per page."""
    s = strip_wikitext(fixture_text("Gandalf"))
    assert extraction_text(s) == s.text[: s.lead_end]
    assert extraction_text(s).startswith("Name: Gandalf\n")
    llm = by_page()
    await fixture_plan(store, wiki, llm, urls=[URLS[1]])
    [[_, human]] = llm.prompts
    assert "Page title: Gandalf\n\n" + s.text[: s.lead_end] in human.content
    assert s.text[s.lead_end : s.lead_end + 200] not in human.content
    # A passage after the lead is not found, so it can't become a body.
    later = s.text[s.lead_end :].split("\n")[1]
    llm = by_page({"Gandalf": cand("Gandalf", later)})
    plan, _, _ = await fixture_plan(store, wiki, llm, urls=[URLS[1]])
    assert [(x.title, x.reason) for x in plan.skipped] == [("Gandalf", NOT_LOCATED)]


async def test_candidate_matching_the_page_title_is_chosen(store, wiki):
    """R-W3-5: the candidate named like the page (title or alias), else the first."""
    other = cand("Bilbo", "Bilbo is not in this lead.")
    llm = by_page({"Gandalf": [other, cand("Mithrandir", LEAD["Gandalf"], aliases=["gandalf"])]})
    plan, _, _ = await fixture_plan(store, wiki, llm, urls=[URLS[1]])
    [p] = plan.proposals
    assert p.after.title == "Gandalf" and p.after.aliases == []
    llm = by_page({"Gandalf": [cand("Mithrandir", LEAD["Gandalf"], aliases=["Grey Pilgrim", "Gandalf"]), other]})
    plan, _, _ = await fixture_plan(store, wiki, llm, urls=[URLS[1]])
    [p] = plan.proposals
    assert p.after.title == "Gandalf" and p.after.aliases == ["Grey Pilgrim"]


async def test_failed_and_empty_extractions_are_listed(store, wiki):
    llm = by_page({"Gandalf": RuntimeError("model down"), "Rivendell": []})
    plan, _, _ = await fixture_plan(store, wiki, llm)
    assert [p.after.title for p in plan.proposals] == ["The Shire"]
    assert [(s.title, s.reason, s.paste) for s in plan.skipped] == [
        ("Rivendell", NOT_LOCATED, False),
        ("Gandalf", PART_FAILED, False),
    ]
    assert (plan.parts, plan.failed_parts) == (3, 1)


async def test_only_invalid_candidates_are_listed_as_invalid(store, wiki):
    content = json.dumps({"candidates": [{"title": "Gandalf", "type": "dragon"}]})
    raw = {"raw": AIMessage(content=content), "parsed": None, "parsing_error": None}
    plan, _, _ = await fixture_plan(store, wiki, StubLLM(raw), urls=[URLS[1]])
    assert plan.proposals == []
    assert [(s.title, s.reason) for s in plan.skipped] == [("Gandalf", INVALID)]


# ---------- fetching: licence, errors, duplicates ----------


async def test_licence_unreadable_stops_before_any_page_request(wiki):
    client, server = wiki(WikiServer({"Gandalf": parse_body("Gandalf", "Synthetic.")}, licence=403), seed=False)
    with pytest.raises(LicenceUnreadable):
        await fetch_wiki(client, parse_page_urls(["https://en.wikipedia.org/wiki/Gandalf"]))
    assert server.parse_requests() == []
    assert [r.url.params.get("meta") for r in server.requests] == ["siteinfo"]


@pytest.mark.parametrize(
    "status, reason",
    [
        (402, BLOCKED.format(code=402)),
        (403, BLOCKED.format(code=403)),
        (429, RATE_LIMITED),
        (404, PAGE_MISSING),
        (500, UNREACHABLE),
    ],
)
async def test_each_error_code_is_listed_with_paste(wiki, status, reason):
    client, server = wiki(WikiServer({"Nowhere Town": status}))
    fetched = await fetch_wiki(client, parse_page_urls(["https://en.wikipedia.org/wiki/Nowhere_Town"]))
    assert fetched.pages == []
    assert fetched.skipped == [Skipped(title="Nowhere Town", reason=reason, paste=True)]
    assert len(server.parse_requests("Nowhere Town")) == 1  # never retried
    assert fetched.requested == 1


async def test_block_stops_further_requests_to_that_host(store, wiki):
    """Review Focus 5 / R-W3-3: after a 402/403, no later page is requested, cached or not."""
    urls = ["https://en.wikipedia.org/wiki/Alpha_Vale", "https://en.wikipedia.org/wiki/Beta_Ford", URLS[1]]
    client, server = wiki(WikiServer({"Alpha Vale": parse_body("Alpha Vale", "Synthetic vale."), "Beta Ford": 403}))
    fetched = await fetch_wiki(client, parse_page_urls(urls))
    assert [p.title for p in fetched.pages] == ["Alpha Vale"]
    assert [(s.title, s.reason, s.paste) for s in fetched.skipped] == [
        ("Beta Ford", BLOCKED.format(code=403), True),
        ("Gandalf", NOT_REQUESTED, True),
    ]
    assert [r.url.params["page"] for r in server.parse_requests()] == ["Alpha Vale", "Beta Ford"]


async def test_unreachable_failures_are_listed_with_paste(wiki):
    off = httpx.Response(302, headers={"location": "https://evil.example.com/x"})
    server = WikiServer({"Off Site": off, "Not Json": httpx.Response(200, text="<html>"), "Odd": api_error("readonly")})
    client, _ = wiki(server)
    urls = [f"https://en.wikipedia.org/wiki/{t}" for t in ("Off_Site", "Not_Json", "Odd")]
    fetched = await fetch_wiki(client, parse_page_urls(urls))
    assert [(s.title, s.reason, s.paste) for s in fetched.skipped] == [
        ("Off Site", UNREACHABLE, True),
        ("Not Json", UNREACHABLE, True),
        ("Odd", UNREACHABLE, True),
    ]


async def test_missing_and_empty_pages_are_listed(store, wiki):
    """Review Focus 2: `missingtitle`/`invalidtitle` are missing pages; a page with no article
    text (a disambiguation template, or an infobox alone) is listed, not extracted."""
    server = WikiServer(
        {
            "Nobody": api_error("missingtitle"),
            "Bad<Title": api_error("invalidtitle"),
            "Mercury": parse_body("Mercury", "{{Disambiguation}}"),
            "Box Only": parse_body("Box Only", "{{Infobox character|name=Box}}\n{{Stub}}"),
        }
    )
    client, _ = wiki(server)
    urls = [f"https://en.wikipedia.org/wiki/{t}" for t in ("Nobody", "Bad%3CTitle", "Mercury", "Box_Only")]
    fetched = await fetch_wiki(client, parse_page_urls(urls))
    llm = by_page()
    plan = await build_wiki_import(store, llm, W, fetched, today=TODAY)
    assert plan.proposals == [] and llm.prompts == []
    assert [(s.title, s.reason, s.paste) for s in plan.skipped] == [
        ("Nobody", PAGE_MISSING, True),
        ("Bad<Title", PAGE_MISSING, True),
        ("Mercury", NO_TEXT, False),
        ("Box Only", NO_TEXT, False),
    ]
    assert (plan.parts, plan.failed_parts) == (0, 0)


async def test_redirected_namespace_page_is_missing(wiki):
    """Carried from Task 3: a redirect that lands on a non-article page (Wikipedia's own, or a
    Fandom forum, blog or message wall) is not imported."""
    server = WikiServer({"WP:NPOV": parse_body("Wikipedia:Neutral point of view", "Synthetic policy.")})
    client, _ = wiki(server)
    fetched = await fetch_wiki(client, parse_page_urls(["https://en.wikipedia.org/wiki/WP:NPOV"]))
    assert fetched.pages == []
    assert fetched.skipped == [Skipped(title="WP:NPOV", reason=PAGE_MISSING, paste=True)]

    fandom = WikiServer(
        {
            "Town Hall": parse_body("Forum:Town Hall", "Synthetic thread."),
            "Diary": parse_body("Blog:Diary", "Synthetic post."),
            "Hello": parse_body("Message Wall:Someone", "Synthetic message."),
            "Harbour": parse_body("Harbour", "The harbour is a synthetic place."),
        },
        licence=rightsinfo_body("CC-BY-SA", "https://creativecommons.org/licenses/by-sa/3.0/"),
    )
    client, _ = wiki(fandom, seed=False)
    urls = [f"https://synthetic.fandom.com/wiki/{t}" for t in ("Town_Hall", "Diary", "Hello", "Harbour")]
    fetched = await fetch_wiki(client, parse_page_urls(urls))
    assert [p.title for p in fetched.pages] == ["Harbour"]
    assert [(s.title, s.reason, s.paste) for s in fetched.skipped] == [
        ("Town Hall", PAGE_MISSING, True),
        ("Diary", PAGE_MISSING, True),
        ("Hello", PAGE_MISSING, True),
    ]


async def test_redirected_duplicate_is_one_proposal(store, wiki):
    """Review Focus 3: two URLs that MediaWiki resolves to one page give one proposal."""
    server = WikiServer({"Gandalf the Grey": parse_body("Gandalf", fixture_text("Gandalf"))})
    client, _ = wiki(server)
    urls = [URLS[1], "https://en.wikipedia.org/wiki/Gandalf_the_Grey"]
    fetched = await fetch_wiki(client, parse_page_urls(urls))
    plan = await build_wiki_import(store, by_page(), W, fetched, today=TODAY)
    assert [p.after.title for p in plan.proposals] == ["Gandalf"]
    assert [(s.title, s.reason, s.paste) for s in plan.skipped] == [("Gandalf the Grey", SAME_PAGE, False)]


# ---------- merges ----------


async def test_wiki_merge_keeps_secrets_and_appends_official_source(store, wiki):
    """Review Focus 4."""
    ref = EntrySource(kind="reference", url="https://en.wikipedia.org/wiki/Hobbit", licence="CC")
    before = seed(
        store, "The Shire", "Green hills of the hobbits.",
        facts=[Fact(key="Hidden Door", value="Under the hill", status="secret")], sources=[ref],
    )
    llm = by_page({"The Shire": cand("The Shire", LEAD["The Shire"], facts=[("Hidden Door", "Behind the mill")])})
    plan, _, _ = await fixture_plan(store, wiki, llm, urls=[URLS[2]])
    [p] = plan.proposals
    assert p.action == "update" and p.entry_id == before.id
    url = URL_OF["The Shire"]
    assert p.after.body == (
        f"Green hills of the hobbits.\n\n## Imported from {url} (2026-11-09)\n\n{LEAD['The Shire']}"
    )
    assert [(f.key, f.value, f.status) for f in p.after.facts] == [("Hidden Door", "Behind the mill", "secret")]
    assert [(s.kind, s.url) for s in p.after.sources] == [("reference", ref.url), ("official", url)]
    assert p.after.sources[0] == ref
    assert p.after.source == "official" and p.after.source_url == url and p.after.trusted is False
    assert p.after.licence == LICENCE["text"]
    assert is_import_merge(before.body, p.after.body)


async def test_merge_label_with_parentheses_survives_save_as_myth(store, wiki):
    """A page title with parentheses in the heading still reads as an import merge, and Save as
    myth (R-W5-11) keeps the imported section."""
    before = seed(store, "Elrond (character)", "Half-elven lord.")
    client, _ = wiki(WikiServer({"Elrond (character)": parse_body("Elrond (character)", ELROND_TEXT)}))
    fetched = await fetch_wiki(client, parse_page_urls([ELROND]))
    excerpt = "Elrond is a synthetic test character who keeps a house in a quiet valley."
    llm = by_page({"Elrond (character)": cand("Elrond", excerpt)})
    plan = await build_wiki_import(store, llm, W, fetched, today=TODAY)
    [p] = plan.proposals
    assert p.action == "update"
    assert f"\n\n## Imported from {ELROND} (2026-11-09)\n\n{excerpt}" in p.after.body
    assert is_import_merge(before.body, p.after.body)
    kept = apply_save_as_myth(p, CheckResult(proposal_id=p.proposal_id, verdict="none"), None, imported=True)
    assert kept.body == p.after.body


async def test_reimport_replaces_earlier_section(store, wiki):
    """Open question 1 (c): a page already among the entry's sources replaces its own earlier
    section, in place, and is not listed as a source twice."""
    url = URL_OF["Gandalf"]
    official = EntrySource(kind="official", url=url, licence=LICENCE["text"], licence_url=LICENCE["url"])
    other = "## Imported from notes.md (2026-01-02)\n\nThe author's own notes."
    seed(
        store, "Gandalf",
        f"Grey pilgrim.\n\n## Imported from {url} (2026-01-01)\n\nAn older lead.\nOf two lines.\n\n{other}",
        sources=[official],
    )
    plan, _, _ = await fixture_plan(store, wiki, urls=[URLS[1]])
    [p] = plan.proposals
    assert p.action == "update"
    assert p.after.body == (
        f"Grey pilgrim.\n\n## Imported from {url} (2026-11-09)\n\n{LEAD['Gandalf']}\n\n{other}"
    )
    assert p.after.sources == [official]
    assert p.after.source == "official" and p.after.trusted is False


async def test_reimport_of_page_without_section_appends(store, wiki):
    """A page that created the entry left no heading to replace: the fresh text is appended."""
    url = URL_OF["Gandalf"]
    official = EntrySource(kind="official", url=url, licence=LICENCE["text"])
    seed(store, "Gandalf", "An earlier lead.", sources=[official])
    plan, _, _ = await fixture_plan(store, wiki, urls=[URLS[1]])
    [p] = plan.proposals
    assert p.after.body == f"An earlier lead.\n\n## Imported from {url} (2026-11-09)\n\n{LEAD['Gandalf']}"
    assert p.after.sources == [official]


async def test_nc_licence_marks_every_source(store, wiki):
    nc_text, nc_url = "CC BY-NC-SA 3.0", "https://creativecommons.org/licenses/by-nc-sa/3.0/"
    server = WikiServer(
        {
            "North Gate": parse_body("North Gate", "The North Gate is a synthetic gate."),
            "South Gate": parse_body("South Gate", "The South Gate is a synthetic gate too."),
        },
        licence=rightsinfo_body(nc_text, nc_url),
    )
    client, _ = wiki(server, seed=False)
    urls = ["https://synthetic.fandom.com/wiki/North_Gate", "https://synthetic.fandom.com/wiki/South_Gate"]
    fetched = await fetch_wiki(client, parse_page_urls(urls))
    llm = by_page(
        {
            "North Gate": cand("North Gate", "The North Gate is a synthetic gate."),
            "South Gate": cand("South Gate", "The South Gate is a synthetic gate too."),
        }
    )
    plan = await build_wiki_import(store, llm, W, fetched, today=TODAY)
    assert len(plan.proposals) == 2
    for p in plan.proposals:
        assert p.after.sources[0].nc is True
        assert (p.after.sources[0].licence, p.after.sources[0].licence_url) == (nc_text, nc_url)
    assert plan.licence == {"text": nc_text, "url": nc_url, "nc": True}


async def test_reimport_replace_survives_save_as_myth(store, wiki):
    """R-W5-11 on the Q1 (c) shape: Save as myth keeps the freshly replaced section."""
    url = URL_OF["Gandalf"]
    official = EntrySource(kind="official", url=url, licence=LICENCE["text"], licence_url=LICENCE["url"])
    before = seed(
        store, "Gandalf",
        f"Grey pilgrim.\n\n## Imported from {url} (2026-01-01)\n\nAn older lead.\n\n"
        "## Imported from notes.md (2026-01-02)\n\nThe author's own notes.",
        sources=[official],
    )
    plan, _, _ = await fixture_plan(store, wiki, urls=[URLS[1]])
    [p] = plan.proposals
    assert is_import_merge(before.body, p.after.body)
    kept = apply_save_as_myth(p, CheckResult(proposal_id=p.proposal_id, verdict="none"), None, imported=True)
    assert kept.body == p.after.body
    assert LEAD["Gandalf"] in kept.body and "An older lead." not in kept.body


async def test_infobox_without_lead_prose_is_no_text(store, wiki):
    """Only the lead is extracted (Q2 (a)): a page whose lead is the infobox alone is listed,
    so a body can never be just infobox lines."""
    wikitext = "{{Infobox character|name=Quiet One|race=Synthetic}}\n== History ==\nA later synthetic section."
    client, _ = wiki(WikiServer({"Quiet One": parse_body("Quiet One", wikitext)}))
    fetched = await fetch_wiki(client, parse_page_urls(["https://en.wikipedia.org/wiki/Quiet_One"]))
    llm = by_page({"Quiet One": cand("Quiet One", "Name: Quiet One")})
    plan = await build_wiki_import(store, llm, W, fetched, today=TODAY)
    assert plan.proposals == [] and llm.prompts == []
    assert [(s.title, s.reason) for s in plan.skipped] == [("Quiet One", NO_TEXT)]


async def test_unexpected_fetch_error_is_unreachable_with_traceback(wiki, monkeypatch, caplog):
    client, _ = wiki()

    async def broken(page):
        raise RuntimeError("a bug in the client")

    monkeypatch.setattr(client, "fetch_page", broken)
    with caplog.at_level("INFO", logger="sagaloom.importing.wiki"):
        fetched = await fetch_wiki(client, parse_page_urls(["https://en.wikipedia.org/wiki/Gandalf"]))
    assert fetched.skipped == [Skipped(title="Gandalf", reason=UNREACHABLE, paste=True)]
    [rec] = [r for r in caplog.records if r.name == "sagaloom.importing.wiki"]
    assert rec.exc_info is not None and isinstance(rec.exc_info[1], RuntimeError)
