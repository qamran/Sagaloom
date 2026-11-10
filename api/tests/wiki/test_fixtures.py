"""The committed Wikipedia fixtures (R-W3-2, F1): Wikipedia only, keyed as the builders key them,
and enough to run the demo offline once seeded."""

import importlib.util
import json
from pathlib import Path

import httpx

from sagaloom.wiki.client import WikiClient
from sagaloom.wiki.pages import parse_page_url, parse_request_url, rightsinfo_url

API = Path(__file__).resolve().parents[2]
FIXTURES = API / "tests" / "fixtures" / "wiki"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))


def _host_ok(url: str) -> bool:
    host = httpx.URL(url).host
    return host == "wikipedia.org" or host.endswith(".wikipedia.org")


def test_manifest_lists_three_pages_and_a_licence():
    assert len(MANIFEST["pages"]) == 3
    assert MANIFEST["licence"]["text"] and MANIFEST["licence"]["url"]


def test_committed_wiki_fixtures_are_wikipedia_only():
    for page in MANIFEST["pages"]:
        assert _host_ok(page["in"]) and _host_ok(page["url"]) and _host_ok(page["parse_request"])
    caches = sorted(FIXTURES.glob("*.v2.json"))
    assert len(caches) == 4
    for cache in caches:
        raw = cache.read_text(encoding="utf-8")
        assert _host_ok(json.loads(raw)["final_url"])
        assert "fandom.com" not in raw
    attribution = (FIXTURES / "ATTRIBUTION.md").read_text(encoding="utf-8")
    for page in MANIFEST["pages"]:
        assert page["url"] in attribution and page["in"] in attribution
    assert MANIFEST["licence"]["text"] in attribution and MANIFEST["licence"]["url"] in attribution


def test_fixture_cache_keys_match_builders(tmp_path):
    client = WikiClient(tmp_path)
    for page in MANIFEST["pages"]:
        name = client._cache_path(parse_request_url(parse_page_url(page["in"]))).name
        assert (FIXTURES / name).is_file()
    assert (FIXTURES / client._cache_path(rightsinfo_url("en.wikipedia.org")).name).is_file()


async def test_seed_wiki_cache_serves_without_network(tmp_path):
    spec = importlib.util.spec_from_file_location("seed_wiki_cache", API / "scripts" / "seed_wiki_cache.py")
    seeder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seeder)
    seeder.seed(tmp_path)
    seeder.seed(tmp_path)  # idempotent

    def refuse(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"network request: {request.url}")

    client = WikiClient(tmp_path / "cache" / "wiki", transport=httpx.MockTransport(refuse))
    try:
        for page in MANIFEST["pages"]:
            fetched = await client.fetch_page(parse_page_url(page["in"]))
            assert fetched.title == page["title"] and fetched.url == page["url"]
            assert fetched.wikitext
        licence = await client.site_licence("en.wikipedia.org")
        assert licence.text == MANIFEST["licence"]["text"]
    finally:
        await client.aclose()
    assert len(list((tmp_path / "cache" / "wiki").glob("*.v2.json"))) == 4
