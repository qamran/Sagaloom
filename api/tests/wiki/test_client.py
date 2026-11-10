"""MediaWiki client tests (R11.4.2, R11.4.4, R-W3-2, R-W3-9). All HTTP goes through
httpx.MockTransport."""

import importlib.metadata
import json

import httpx
import pytest

from sagaloom.wiki.client import (
    USER_AGENT,
    HostNotAllowed,
    LicenceUnreadable,
    WikiApiError,
    WikiClient,
    search_and_summarise,
)
from sagaloom.wiki.pages import parse_page_url, parse_request_url, rightsinfo_url

SEARCH = "https://en.wikipedia.org/w/api.php"
SHIRE = "https://en.wikipedia.org/wiki/Shire_(Middle-earth)"
CC_BY_SA = "Creative Commons Attribution-Share Alike 4.0"
CC_URL = "https://creativecommons.org/licenses/by-sa/4.0/"


def counting(handler):
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return httpx.MockTransport(wrapped), seen


def quick(tmp_path, transport, **kw) -> WikiClient:
    """A client that never sleeps for real (the throttle has its own test)."""

    async def no_sleep(seconds: float) -> None:
        return None

    return WikiClient(tmp_path, transport=transport, sleep=no_sleep, **kw)


def parse_body(title="Shire (Middle-earth)", **extra) -> dict:
    return {
        "parse": {
            "title": title,
            "pageid": 1,
            "revid": 42,
            "wikitext": "The '''Shire''' is a region.",
            "categories": [{"sortkey": "", "category": "Middle-earth_regions"}, {"category": "Hobbits"}],
            **extra,
        }
    }


async def test_rejects_other_hosts(tmp_path):
    transport, seen = counting(lambda r: httpx.Response(200, json={}))
    client = quick(tmp_path, transport)
    for url in [
        "https://evil.example/x",
        "https://wikipedia.org.evil.example/x",
        "http://en.wikipedia.org/w/api.php",
        "https://evilfandom.com/api.php",
    ]:
        with pytest.raises(HostNotAllowed):
            await client.get_json(url)
    assert seen == []
    assert await client.get_json("https://x.fandom.com/api.php") == {}
    assert len(seen) == 1
    await client.aclose()


async def test_user_agent_is_honest(tmp_path):
    version = importlib.metadata.version("sagaloom")
    assert USER_AGENT == f"Sagaloom/{version} (+https://github.com/qamran/Sagaloom)"
    assert "Mozilla" not in USER_AGENT
    transport, seen = counting(lambda r: httpx.Response(200, json={"ok": 1}))
    client = quick(tmp_path, transport)
    await client.get_json(f"{SEARCH}?a=1")
    await client.get_json("https://lotr.fandom.com/api.php?a=2")
    await client.aclose()
    assert len(seen) == 2
    assert all(r.headers["User-Agent"] == USER_AGENT for r in seen)


async def test_sends_user_agent_and_caches(tmp_path):
    transport, seen = counting(lambda r: httpx.Response(200, json={"ok": 1}))
    client = quick(tmp_path / "cache", transport)
    url = f"{SEARCH}?action=query&list=search&format=json&srlimit=3&srsearch=Byzantium"
    assert await client.get_json(url) == {"ok": 1}
    assert len(seen) == 1 and seen[0].headers["User-Agent"] == USER_AGENT
    assert await client.get_json(url) == {"ok": 1}
    assert len(seen) == 1
    assert len(list((tmp_path / "cache").glob("*.v2.json"))) == 1
    await client.aclose()


async def test_cache_v2_holds_final_url_and_ignores_old_files(tmp_path):
    transport, seen = counting(lambda r: httpx.Response(200, json={"ok": 2}))
    client = quick(tmp_path, transport)
    url = f"{SEARCH}?a=1"
    path = client._cache_path(url)
    assert path.name.endswith(".v2.json")
    path.with_name(path.name.replace(".v2.json", ".json")).write_text('{"stale": true}', encoding="utf-8")
    assert await client.get_json_final(url) == ({"ok": 2}, url)
    assert len(seen) == 1
    assert json.loads(path.read_text(encoding="utf-8")) == {"final_url": url, "body": {"ok": 2}}
    await client.aclose()


async def test_one_shared_http_client(tmp_path):
    transport, seen = counting(lambda r: httpx.Response(200, json={"ok": 1}))
    client = quick(tmp_path, transport)
    assert client._http is None  # created on first use, inside the loop
    await client.get_json(f"{SEARCH}?a=1")
    first = client._http
    await client.get_json(f"{SEARCH}?a=2")
    assert first is not None and client._http is first
    await client.aclose()
    assert client._http is None
    await client.aclose()  # closing twice is harmless


async def test_summary_path_is_encoded(tmp_path):
    title = "AC/DC? Ünïcode"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/w/api.php":
            assert request.url.params["srsearch"] == "acdc"
            assert request.url.params["srlimit"] == "1"
            return httpx.Response(200, json={"query": {"search": [{"title": title}]}})
        return httpx.Response(200, json={"title": title, "extract": "A band."})

    transport, seen = counting(handler)
    client = quick(tmp_path, transport)
    results = await search_and_summarise(client, "acdc", 1)
    await client.aclose()
    assert seen[1].url.raw_path == b"/api/rest_v1/page/summary/AC%2FDC%3F_%C3%9Cn%C3%AFcode"
    assert [r.title for r in results] == [title]
    assert results[0].url.startswith("https://en.wikipedia.org/wiki/")


async def test_timeout_raises(tmp_path):
    def boom(request):
        raise httpx.ReadTimeout("slow", request=request)

    client = quick(tmp_path, httpx.MockTransport(boom))
    with pytest.raises(httpx.TimeoutException):
        await client.get_json(f"{SEARCH}?action=query")
    await client.aclose()
    assert list(tmp_path.glob("*.json")) == []  # failures are never cached


async def test_failed_cache_write_leaves_no_temp_file(tmp_path, monkeypatch):
    import sagaloom.wiki.client as client_module

    def deny(src, dst):
        raise PermissionError("locked")

    monkeypatch.setattr(client_module.os, "replace", deny)
    transport, _ = counting(lambda r: httpx.Response(200, json={"ok": 1}))
    client = quick(tmp_path, transport)
    assert await client.get_json(f"{SEARCH}?action=query") == {"ok": 1}
    await client.aclose()
    assert list(tmp_path.iterdir()) == []


async def test_redirect_followed_on_allowed_hosts(tmp_path):
    start = f"{SEARCH}?action=parse&page=Shire"
    final = "https://en.wikipedia.org/w/api.php?action=parse&page=Shire_(Middle-earth)"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "en.wikipedia.org" and "Middle-earth" not in str(request.url):
            return httpx.Response(301, headers={"Location": "https://en.m.wikipedia.org/w/api.php?x=1"})
        if request.url.host == "en.m.wikipedia.org":
            return httpx.Response(301, headers={"Location": "//en.wikipedia.org/w/api.php?action=parse&page=Shire_(Middle-earth)"})
        return httpx.Response(200, json={"ok": "final"})

    transport, seen = counting(handler)
    client = quick(tmp_path, transport)
    body, url = await client.get_json_final(start)
    assert body == {"ok": "final"}
    assert url == str(httpx.URL(final))
    assert [r.url.host for r in seen] == ["en.wikipedia.org", "en.m.wikipedia.org", "en.wikipedia.org"]
    # The cached copy keeps the final URL.
    assert await client.get_json_final(start) == (body, url)
    assert len(seen) == 3
    await client.aclose()


async def test_redirect_hop_off_allowlist_is_refused(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "en.wikipedia.org":
            return httpx.Response(302, headers={"Location": "https://evil.example/x"})
        return httpx.Response(200, json={"stolen": True})

    transport, seen = counting(handler)
    client = quick(tmp_path, transport)
    with pytest.raises(HostNotAllowed):
        await client.get_json(f"{SEARCH}?a=1")
    assert [r.url.host for r in seen] == ["en.wikipedia.org"]
    assert not any(r.url.host == "evil.example" for r in seen)
    assert list(tmp_path.glob("*.json")) == []
    await client.aclose()


@pytest.mark.parametrize(
    "location",
    ["http://en.wikipedia.org/w/api.php", "https://en.wikipedia.org:8443/w/api.php", "https://u@en.wikipedia.org/"],
)
async def test_redirect_to_unsafe_form_of_allowed_host_is_refused(tmp_path, location):
    transport, seen = counting(lambda r: httpx.Response(307, headers={"Location": location}))
    client = quick(tmp_path, transport)
    with pytest.raises(HostNotAllowed):
        await client.get_json(f"{SEARCH}?a=1")
    assert len(seen) == 1
    await client.aclose()


async def test_too_many_redirects(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        n = int(request.url.params.get("n", "0"))
        return httpx.Response(302, headers={"Location": f"/w/api.php?n={n + 1}"})

    transport, seen = counting(handler)
    client = quick(tmp_path, transport)
    with pytest.raises(httpx.TooManyRedirects):
        await client.get_json(f"{SEARCH}?n=0")
    assert len(seen) == 6  # the first request and five followed hops; the sixth hop is refused
    assert list(tmp_path.glob("*.json")) == []
    await client.aclose()


async def test_five_redirects_are_followed(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        n = int(request.url.params.get("n", "0"))
        if n == 5:
            return httpx.Response(200, json={"n": n})
        return httpx.Response(308, headers={"Location": f"/w/api.php?n={n + 1}"})

    transport, seen = counting(handler)
    client = quick(tmp_path, transport)
    assert await client.get_json(f"{SEARCH}?n=0") == {"n": 5}
    assert len(seen) == 6
    await client.aclose()


@pytest.mark.parametrize("status", [402, 403, 429, 503])
async def test_no_retry_on_block(tmp_path, status):
    transport, seen = counting(lambda r: httpx.Response(status, json={"error": "blocked"}))
    client = quick(tmp_path, transport)
    with pytest.raises(httpx.HTTPStatusError) as info:
        await client.get_json(f"{SEARCH}?a=1")
    assert info.value.response.status_code == status
    assert len(seen) == 1
    with pytest.raises(httpx.HTTPStatusError):
        await client.get_json(f"{SEARCH}?a=1")
    assert len(seen) == 2  # nothing was cached
    assert list(tmp_path.glob("*.json")) == []
    await client.aclose()


async def test_throttle_waits_between_real_requests_per_host(tmp_path):
    now = [100.0]
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    transport, seen = counting(lambda r: httpx.Response(200, json={"ok": 1}))
    client = WikiClient(tmp_path, transport=transport, clock=lambda: now[0], sleep=sleep)
    await client.get_json(f"{SEARCH}?a=1")
    assert slept == []  # the first request to a host never waits
    now[0] += 0.25
    await client.get_json(f"{SEARCH}?a=2")
    assert slept == [pytest.approx(0.75)]
    await client.get_json(f"{SEARCH}?a=3")
    assert slept == [pytest.approx(0.75), pytest.approx(1.0)]
    await client.get_json("https://lotr.fandom.com/api.php?a=1")  # another host
    assert len(slept) == 2
    await client.get_json(f"{SEARCH}?a=1")  # a cache hit
    assert len(slept) == 2
    assert len(seen) == 4
    now[0] += 5.0
    await client.get_json(f"{SEARCH}?a=4")  # long enough ago: no wait
    assert len(slept) == 2
    await client.aclose()


async def test_throttle_applies_to_each_redirect_hop(tmp_path):
    now = [0.0]
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("n") == "0":
            return httpx.Response(302, headers={"Location": "/w/api.php?n=1"})
        return httpx.Response(200, json={"ok": 1})

    transport, _ = counting(handler)
    client = WikiClient(tmp_path, transport=transport, clock=lambda: now[0], sleep=sleep)
    await client.get_json(f"{SEARCH}?n=0")
    assert slept == [pytest.approx(1.0)]
    await client.aclose()


async def test_api_error_body_is_not_cached(tmp_path):
    transport, seen = counting(lambda r: httpx.Response(200, json={"error": {"code": "missingtitle", "info": "x"}}))
    client = quick(tmp_path, transport)
    page = parse_page_url("https://en.wikipedia.org/wiki/Nowhere")
    with pytest.raises(WikiApiError) as info:
        await client.fetch_page(page)
    assert info.value.code == "missingtitle"
    with pytest.raises(WikiApiError):
        await client.fetch_page(page)
    assert len(seen) == 2
    assert list(tmp_path.glob("*.json")) == []
    await client.aclose()


async def test_fetch_page_reads_parse_and_builds_url(tmp_path):
    transport, seen = counting(lambda r: httpx.Response(200, json=parse_body(url="https://evil.example/x")))
    client = quick(tmp_path, transport)
    page = parse_page_url("https://en.wikipedia.org/wiki/Shire%20(Middle-earth)?oldid=1")
    fetched = await client.fetch_page(page)
    assert fetched.page == page
    assert fetched.title == "Shire (Middle-earth)"
    assert fetched.url == SHIRE
    assert fetched.wikitext == "The '''Shire''' is a region."
    assert fetched.categories == ["Middle-earth_regions", "Hobbits"]
    assert fetched.revid == 42
    assert str(seen[0].url) == str(httpx.URL(parse_request_url(page)))
    await client.aclose()


async def test_fetch_page_uses_the_mediawiki_redirect_title(tmp_path):
    transport, _ = counting(lambda r: httpx.Response(200, json=parse_body(title="Gandalf")))
    client = quick(tmp_path, transport)
    fetched = await client.fetch_page(parse_page_url("https://en.wikipedia.org/wiki/Gandalf_the_Grey"))
    assert (fetched.title, fetched.url) == ("Gandalf", "https://en.wikipedia.org/wiki/Gandalf")
    await client.aclose()


async def test_fetch_page_url_is_on_the_final_host(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "starwars.fandom.com":
            return httpx.Response(301, headers={"Location": "https://starwars-de.fandom.com/de/api.php?x=1"})
        return httpx.Response(200, json=parse_body(title="Yoda"))

    transport, _ = counting(handler)
    client = quick(tmp_path, transport)
    fetched = await client.fetch_page(parse_page_url("https://starwars.fandom.com/de/wiki/Yoda"))
    assert fetched.url == "https://starwars-de.fandom.com/de/wiki/Yoda"
    await client.aclose()


async def test_fetch_page_without_parse_is_an_error(tmp_path):
    transport, _ = counting(lambda r: httpx.Response(200, json={"batchcomplete": True}))
    client = quick(tmp_path, transport)
    with pytest.raises(ValueError):
        await client.fetch_page(parse_page_url("https://en.wikipedia.org/wiki/Gandalf"))
    await client.aclose()


def licence_handler(rightsinfo):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("meta") == "siteinfo":
            return httpx.Response(200, json={"batchcomplete": True, "query": {"rightsinfo": rightsinfo}})
        return httpx.Response(200, json=parse_body())

    return handler


async def test_only_api_endpoints_are_requested(tmp_path):
    transport, seen = counting(licence_handler({"url": CC_URL, "text": CC_BY_SA}))
    client = quick(tmp_path, transport)
    await client.fetch_page(parse_page_url(SHIRE))
    await client.site_licence("en.wikipedia.org")
    await client.fetch_page(parse_page_url("https://starwars.fandom.com/de/wiki/Yoda"))
    await client.site_licence("starwars.fandom.com", "/de")
    assert len(seen) == 4
    assert all(r.url.path.endswith("/api.php") for r in seen)
    assert all(r.method == "GET" for r in seen)
    await client.aclose()


async def test_site_licence_reads_rightsinfo_exactly(tmp_path):
    transport, seen = counting(licence_handler({"url": CC_URL, "text": CC_BY_SA}))
    client = quick(tmp_path / "a", transport)
    licence = await client.site_licence("en.wikipedia.org")
    assert licence.text == CC_BY_SA and licence.url == CC_URL
    assert licence.nc is False
    assert licence.display == CC_BY_SA
    assert str(seen[0].url) == str(httpx.URL(rightsinfo_url("en.wikipedia.org")))
    await client.aclose()

    nc_text = "CC BY-NC-SA 3.0"
    transport, _ = counting(licence_handler({"url": "", "text": nc_text}))
    client = quick(tmp_path / "b", transport)
    licence = await client.site_licence("lotr.fandom.com")
    assert (licence.text, licence.url, licence.nc) == (nc_text, None, True)
    await client.aclose()

    transport, _ = counting(licence_handler({"url": CC_URL, "text": ""}))
    client = quick(tmp_path / "c", transport)
    licence = await client.site_licence("lotr.fandom.com")
    assert (licence.text, licence.display) == (None, CC_URL)
    await client.aclose()


@pytest.mark.parametrize(
    "reply",
    [
        httpx.Response(200, json={"query": {"rightsinfo": {"url": "", "text": ""}}}),
        httpx.Response(200, json={"query": {"rightsinfo": {}}}),
        httpx.Response(200, json={"query": {}}),
        httpx.Response(200, json={"error": {"code": "internal_api_error"}}),
        httpx.Response(403, json={"error": "blocked"}),
        httpx.Response(200, text="<html>not json</html>"),
    ],
    ids=["empty", "missing-fields", "no-rightsinfo", "api-error", "403", "not-json"],
)
async def test_site_licence_unreadable(tmp_path, reply):
    transport, seen = counting(lambda r: reply)
    client = quick(tmp_path, transport)
    with pytest.raises(LicenceUnreadable) as info:
        await client.site_licence("lotr.fandom.com")
    assert info.value.host == "lotr.fandom.com"
    assert len(seen) == 1
    await client.aclose()


async def test_site_licence_timeout_is_unreadable(tmp_path):
    def boom(request):
        raise httpx.ConnectTimeout("slow", request=request)

    client = quick(tmp_path, httpx.MockTransport(boom))
    with pytest.raises(LicenceUnreadable):
        await client.site_licence("en.wikipedia.org")
    await client.aclose()
