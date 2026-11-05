"""MediaWiki client tests (R11.4.2, R11.4.4). All HTTP goes through httpx.MockTransport."""

import httpx
import pytest

from sagaloom.wiki.client import USER_AGENT, HostNotAllowed, WikiClient, search_and_summarise

SEARCH = "https://en.wikipedia.org/w/api.php"


def counting(handler):
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return httpx.MockTransport(wrapped), seen


async def test_rejects_other_hosts(tmp_path):
    transport, seen = counting(lambda r: httpx.Response(200, json={}))
    client = WikiClient(tmp_path, transport=transport)
    for url in [
        "https://evil.example/x",
        "https://wikipedia.org.evil.example/x",
        "http://en.wikipedia.org/w/api.php",
    ]:
        with pytest.raises(HostNotAllowed):
            await client.get_json(url)
    assert seen == []


async def test_sends_user_agent_and_caches(tmp_path):
    assert USER_AGENT == "Sagaloom/0.2 (+https://github.com/qamran/Sagaloom)"
    transport, seen = counting(lambda r: httpx.Response(200, json={"ok": 1}))
    client = WikiClient(tmp_path / "cache", transport=transport)
    url = f"{SEARCH}?action=query&list=search&format=json&srlimit=3&srsearch=Byzantium"
    assert await client.get_json(url) == {"ok": 1}
    assert len(seen) == 1 and seen[0].headers["User-Agent"] == USER_AGENT
    assert await client.get_json(url) == {"ok": 1}
    assert len(seen) == 1
    assert len(list((tmp_path / "cache").glob("*.json"))) == 1


async def test_summary_path_is_encoded(tmp_path):
    title = "AC/DC? Ünïcode"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/w/api.php":
            assert request.url.params["srsearch"] == "acdc"
            assert request.url.params["srlimit"] == "1"
            return httpx.Response(200, json={"query": {"search": [{"title": title}]}})
        return httpx.Response(200, json={"title": title, "extract": "A band."})

    transport, seen = counting(handler)
    results = await search_and_summarise(WikiClient(tmp_path, transport=transport), "acdc", 1)
    assert seen[1].url.raw_path == b"/api/rest_v1/page/summary/AC%2FDC%3F_%C3%9Cn%C3%AFcode"
    assert [r.title for r in results] == [title]
    assert results[0].url.startswith("https://en.wikipedia.org/wiki/")


async def test_timeout_raises(tmp_path):
    def boom(request):
        raise httpx.ReadTimeout("slow", request=request)

    client = WikiClient(tmp_path, transport=httpx.MockTransport(boom))
    with pytest.raises(httpx.HTTPError):
        await client.get_json(f"{SEARCH}?action=query")
    assert list(tmp_path.glob("*.json")) == []  # failures are never cached
