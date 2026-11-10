"""`real_world_reference` tool tests (R11.4.1, R11.4.3, R11.4.7). HTTP is faked."""

import json

import httpx
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from sagaloom.tools.canon_tools import reference_urls_this_turn
from sagaloom.tools.reference import make_reference_tool
from sagaloom.wiki.client import WikiClient
from sagaloom.wiki.pages import parse_page_url

WRAP = '<untrusted_data source="real_world_reference (reference, not canon)">'
LONG = ("word " * 400).strip()  # 1999 characters
LICENCE_TEXT = "Creative Commons Attribution-Share Alike 4.0"
LICENCE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"


def is_rightsinfo(request: httpx.Request) -> bool:
    return request.url.path == "/w/api.php" and request.url.params.get("meta") == "siteinfo"


def rightsinfo() -> httpx.Response:
    return httpx.Response(200, json={"query": {"rightsinfo": {"text": LICENCE_TEXT, "url": LICENCE_URL}}})


def wiki(tmp_path, summaries: dict[str, str], requests: list | None = None, licence_status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        if is_rightsinfo(request):
            return rightsinfo() if licence_status == 200 else httpx.Response(licence_status)
        if request.url.path == "/w/api.php":
            return httpx.Response(200, json={"query": {"search": [{"title": t} for t in summaries]}})
        title = request.url.path.rsplit("/", 1)[1].replace("_", " ")
        return httpx.Response(200, json={"title": title, "extract": summaries[title]})

    return WikiClient(tmp_path, transport=httpx.MockTransport(handler), min_interval=0)


def unwrap(out: str) -> dict:
    assert out.startswith(WRAP) and out.endswith("</untrusted_data>")
    return json.loads(out.split("\n", 1)[1].rsplit("\n", 1)[0])


async def test_reference_output_shape(tmp_path):
    tool = make_reference_tool(wiki(tmp_path, {"Silk Road": LONG, "Venice": "A city on a lagoon."}))
    assert tool.name == "real_world_reference"
    out = await tool.ainvoke({"query": "trade routes", "max_results": 2})
    payload = unwrap(out)
    assert payload["label"] == "reference"
    assert set(payload) == {"label", "results", "licence"}
    silk, venice = payload["results"]
    assert set(silk) == {"title", "summary", "url"}
    assert len(silk["summary"]) <= 1000 and silk["summary"].endswith("…")
    assert silk["summary"][:-1].endswith("word")  # cut at a word boundary
    assert silk["url"] == "https://en.wikipedia.org/wiki/Silk_Road"
    assert venice["summary"] == "A city on a lagoon."


async def test_reference_url_matches_an_imported_page_url(tmp_path):
    """One encoder for page URLs, so a reference source and a wiki import of the same page
    carry the same URL (and `union_sources` dedupes them)."""
    client = wiki(tmp_path, {"Shire (Middle-earth)": "A region."})
    out = await make_reference_tool(client).ainvoke({"query": "shire", "max_results": 1})
    await client.aclose()
    [shire] = unwrap(out)["results"]
    assert shire["url"] == parse_page_url("https://en.wikipedia.org/wiki/Shire_(Middle-earth)").url
    assert shire["url"] == "https://en.wikipedia.org/wiki/Shire_(Middle-earth)"


async def test_reference_payload_carries_licence(tmp_path):
    out = await make_reference_tool(wiki(tmp_path, {"Venice": "A city."})).ainvoke({"query": "venice"})
    assert unwrap(out)["licence"] == {"text": LICENCE_TEXT, "url": LICENCE_URL, "nc": False}


async def test_reference_works_when_licence_unreadable(tmp_path):
    client = wiki(tmp_path, {"Venice": "A city."}, licence_status=503)
    payload = unwrap(await make_reference_tool(client).ainvoke({"query": "venice"}))
    assert [r["title"] for r in payload["results"]] == ["Venice"]
    assert payload["licence"] is None


async def test_licence_lookup_is_cached_per_host(tmp_path):
    requests: list = []
    tool = make_reference_tool(wiki(tmp_path, {"Venice": "A city."}, requests))
    first = unwrap(await tool.ainvoke({"query": "venice"}))
    second = unwrap(await tool.ainvoke({"query": "canals"}))
    assert first["licence"] == second["licence"] is not None
    assert len([r for r in requests if is_rightsinfo(r)]) == 1


async def test_reference_schema_limits(tmp_path):
    tool = make_reference_tool(wiki(tmp_path, {}))
    props = tool.tool_call_schema.model_json_schema()["properties"]
    assert set(props) == {"query", "max_results"}
    assert props["query"]["maxLength"] == 200 and props["query"]["minLength"] == 1
    assert props["max_results"]["default"] == 3
    assert props["max_results"]["minimum"] == 1 and props["max_results"]["maximum"] == 5


async def test_reference_failure_is_soft(tmp_path):
    def boom(request):
        raise httpx.ReadTimeout("slow", request=request)

    tool = make_reference_tool(WikiClient(tmp_path, transport=httpx.MockTransport(boom), min_interval=0))
    out = await tool.ainvoke({"query": "Byzantine trade routes"})
    assert not out.startswith("<untrusted_data")
    err = json.loads(out)["error"]
    assert err.startswith("Wikipedia lookup unavailable: ")


async def test_one_failed_summary_drops_that_title(tmp_path):
    """R11.4.7 per title: one summary 503 loses that title, not the whole lookup."""
    requests: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if is_rightsinfo(request):
            return rightsinfo()
        if request.url.path == "/w/api.php":
            return httpx.Response(200, json={"query": {"search": [{"title": t} for t in ("Venice", "Genoa", "Pisa")]}})
        title = request.url.path.rsplit("/", 1)[1]
        if title == "Genoa":
            return httpx.Response(503)
        return httpx.Response(200, json={"title": title, "extract": f"{title} is a city."})

    client = WikiClient(tmp_path, transport=httpx.MockTransport(handler), min_interval=0)
    payload = unwrap(await make_reference_tool(client).ainvoke({"query": "ports", "max_results": 3}))
    await client.aclose()
    assert [r["title"] for r in payload["results"]] == ["Venice", "Pisa"]
    summaries = [r.url.path.rsplit("/", 1)[1] for r in requests if "/page/summary/" in r.url.path]
    assert sorted(summaries) == ["Genoa", "Pisa", "Venice"]  # one request each, no retry


async def test_search_failure_with_working_licence_is_soft(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return rightsinfo() if is_rightsinfo(request) else httpx.Response(503)

    client = WikiClient(tmp_path, transport=httpx.MockTransport(handler), min_interval=0)
    out = await make_reference_tool(client).ainvoke({"query": "venice"})
    await client.aclose()
    assert not out.startswith("<untrusted_data")  # nothing wrapped, the licence unused
    assert json.loads(out) == {"error": "Wikipedia lookup unavailable: HTTP 503"}


async def test_reference_bad_json_is_soft(tmp_path):
    transport = httpx.MockTransport(lambda r: httpx.Response(200, text="<html>not json"))
    out = await make_reference_tool(WikiClient(tmp_path, transport=transport, min_interval=0)).ainvoke({"query": "x"})
    assert json.loads(out)["error"].startswith("Wikipedia lookup unavailable: ")


def _ref_msg(urls, call_id="c1"):
    body = json.dumps({"label": "reference", "results": [{"title": "t", "summary": "s", "url": u} for u in urls]})
    return ToolMessage(content=f"{WRAP}\n{body}\n</untrusted_data>", tool_call_id=call_id, name="real_world_reference")


def test_reference_urls_this_turn_is_turn_scoped():
    old = _ref_msg(["https://en.wikipedia.org/wiki/Old"], "c0")
    new = _ref_msg(["https://en.wikipedia.org/wiki/A", "https://en.wikipedia.org/wiki/B"])
    msgs = [HumanMessage("turn 1"), AIMessage(""), old, AIMessage("done"), HumanMessage("turn 2")]
    assert reference_urls_this_turn(msgs) == []
    msgs += [AIMessage(""), new, HumanMessage(name="review", content="Review: ...")]
    assert reference_urls_this_turn(msgs) == [
        "https://en.wikipedia.org/wiki/A",
        "https://en.wikipedia.org/wiki/B",
    ]
    assert reference_urls_this_turn([]) == []
