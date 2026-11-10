"""Wiki page URL tests (R-W3-8, R-W3-12). The vectors are shared with the web (Task 8)."""

import json
from pathlib import Path

import httpx
import pytest

from sagaloom.wiki.pages import (
    MAX_URLS,
    BadWikiUrl,
    api_url,
    host_allowed,
    page_key,
    parse_page_url,
    parse_page_urls,
    parse_request_url,
    rightsinfo_url,
)

VECTORS = json.loads((Path(__file__).parents[1] / "fixtures" / "wiki_urls.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", VECTORS["accept"], ids=lambda c: c["in"])
def test_parse_page_url_vectors_accept(case):
    page = parse_page_url(case["in"])
    assert (page.url, page.host, page.lang_path, page.title) == (
        case["url"],
        case["host"],
        case["lang_path"],
        case["title"],
    )


@pytest.mark.parametrize("case", VECTORS["reject"], ids=lambda c: c["in"][:40])
def test_parse_page_url_vectors(case):
    with pytest.raises(BadWikiUrl) as info:
        parse_page_url(case["in"])
    assert str(info.value) == case["error"]


@pytest.mark.parametrize("case", VECTORS["lists"], ids=lambda c: str(c["error"])[:30])
def test_parse_page_urls_lists(case):
    for given in (case["in"], "\n".join(case["in"])):
        if case["error"] is None:
            pages = parse_page_urls(given)
            assert [p.url for p in pages] == [parse_page_url(line).url for line in case["in"] if line.strip()]
        else:
            with pytest.raises(BadWikiUrl) as info:
                parse_page_urls(given)
            assert str(info.value) == case["error"]


def test_vectors_cover_the_caps():
    counts = [len(c["in"]) for c in VECTORS["lists"]]
    assert 0 in counts and MAX_URLS + 1 in counts


def test_page_key_folds_only_the_first_letter():
    a = parse_page_url("https://en.wikipedia.org/wiki/gandalf_the_Grey")
    b = parse_page_url("https://en.wikipedia.org/wiki/Gandalf_the_Grey")
    c = parse_page_url("https://en.wikipedia.org/wiki/Gandalf_the_grey")
    assert page_key(a) == page_key(b) == ("en.wikipedia.org", "", "Gandalf the Grey")
    assert page_key(c) != page_key(b)


def test_api_and_rightsinfo_urls():
    assert api_url("en.wikipedia.org", "") == "https://en.wikipedia.org/w/api.php"
    assert api_url("starwars.fandom.com", "/de") == "https://starwars.fandom.com/de/api.php"
    assert api_url("lotr.fandom.com", "") == "https://lotr.fandom.com/api.php"

    parse = parse_request_url(parse_page_url("https://en.wikipedia.org/wiki/Shire_(Middle-earth)"))
    assert parse.startswith("https://en.wikipedia.org/w/api.php?")
    assert "redirects=1" in parse and "prop=wikitext%7Ccategories" in parse
    params = httpx.URL(parse).params
    assert dict(params) == {
        "action": "parse",
        "format": "json",
        "formatversion": "2",
        "page": "Shire (Middle-earth)",
        "prop": "wikitext|categories",
        "redirects": "1",
    }

    info = httpx.URL(rightsinfo_url("starwars.fandom.com", "/de"))
    assert str(info).startswith("https://starwars.fandom.com/de/api.php?")
    assert dict(info.params) == {
        "action": "query",
        "meta": "siteinfo",
        "siprop": "rightsinfo",
        "format": "json",
        "formatversion": "2",
    }
    assert rightsinfo_url("en.wikipedia.org").startswith("https://en.wikipedia.org/w/api.php?")


@pytest.mark.parametrize(
    "url, allowed",
    [
        ("https://en.wikipedia.org/w/api.php", True),
        ("https://wikipedia.org/", True),
        ("https://x.fandom.com/api.php", True),
        ("https://en.wikipedia.org:443/w/api.php", True),
        ("https://user@en.wikipedia.org/w/api.php", False),
        ("https://user:pw@en.wikipedia.org/w/api.php", False),
        ("https://en.wikipedia.org:8443/w/api.php", False),
        ("https://en.wikipedia.org./w/api.php", False),
        ("http://en.wikipedia.org/w/api.php", False),
        ("https://evilwikipedia.org/", False),
        ("https://evilfandom.com/", False),
        ("https://en.wikipedia.org.evil.com/", False),
    ],
)
def test_host_allowed_edges(url, allowed):
    assert host_allowed(httpx.URL(url)) is allowed
