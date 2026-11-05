"""`real_world_reference` tool tests (R11.4.1, R11.4.3, R11.4.7). HTTP is faked."""

import json

import httpx
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from sagaloom.tools.canon_tools import reference_urls_this_turn
from sagaloom.tools.reference import make_reference_tool
from sagaloom.wiki.client import WikiClient

WRAP = '<untrusted_data source="real_world_reference (reference, not canon)">'
LONG = ("word " * 400).strip()  # 1999 characters


def wiki(tmp_path, summaries: dict[str, str]):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/w/api.php":
            return httpx.Response(200, json={"query": {"search": [{"title": t} for t in summaries]}})
        title = request.url.path.rsplit("/", 1)[1].replace("_", " ")
        return httpx.Response(200, json={"title": title, "extract": summaries[title]})

    return WikiClient(tmp_path, transport=httpx.MockTransport(handler))


def unwrap(out: str) -> dict:
    assert out.startswith(WRAP) and out.endswith("</untrusted_data>")
    return json.loads(out.split("\n", 1)[1].rsplit("\n", 1)[0])


async def test_reference_output_shape(tmp_path):
    tool = make_reference_tool(wiki(tmp_path, {"Silk Road": LONG, "Venice": "A city on a lagoon."}))
    assert tool.name == "real_world_reference"
    out = await tool.ainvoke({"query": "trade routes", "max_results": 2})
    payload = unwrap(out)
    assert payload["label"] == "reference"
    silk, venice = payload["results"]
    assert set(silk) == {"title", "summary", "url"}
    assert len(silk["summary"]) <= 1000 and silk["summary"].endswith("…")
    assert silk["summary"][:-1].endswith("word")  # cut at a word boundary
    assert silk["url"] == "https://en.wikipedia.org/wiki/Silk_Road"
    assert venice["summary"] == "A city on a lagoon."


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

    tool = make_reference_tool(WikiClient(tmp_path, transport=httpx.MockTransport(boom)))
    out = await tool.ainvoke({"query": "Byzantine trade routes"})
    assert not out.startswith("<untrusted_data")
    err = json.loads(out)["error"]
    assert err.startswith("Wikipedia lookup unavailable: ")


async def test_reference_bad_json_is_soft(tmp_path):
    transport = httpx.MockTransport(lambda r: httpx.Response(200, text="<html>not json"))
    out = await make_reference_tool(WikiClient(tmp_path, transport=transport)).ainvoke({"query": "x"})
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
