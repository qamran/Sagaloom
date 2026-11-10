"""A `WikiClient` for tests: a cache seeded from the committed Wikipedia fixtures, and an
`httpx.MockTransport` that answers synthetic pages (synthetic text, never Fandom content) and
records every request. Importable as `wikifakes` from any test directory."""

import json
import shutil
from pathlib import Path

import httpx

from sagaloom.wiki.client import WikiClient

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "wiki"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
LICENCE = MANIFEST["licence"]
FIXTURE_PAGES = MANIFEST["pages"]  # Rivendell, Gandalf, The Shire


def seed_cache(cache_dir: Path) -> Path:
    """The committed fixtures copied into `cache_dir`, as `scripts/seed_wiki_cache.py` does."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    for f in FIXTURES.glob("*.v2.json"):
        shutil.copyfile(f, cache_dir / f.name)
    return cache_dir


def parse_body(title: str, wikitext: str) -> dict:
    return {"parse": {"title": title, "pageid": 1, "revid": 7, "wikitext": wikitext, "categories": []}}


def rightsinfo_body(text: str | None, url: str | None) -> dict:
    return {"batchcomplete": True, "query": {"rightsinfo": {"text": text, "url": url}}}


def api_error(code: str) -> dict:
    return {"error": {"code": code, "info": "synthetic"}}


class WikiServer:
    """Answers `action=parse` by the `page` parameter and `rightsinfo` from `licence`. A value is
    an int (that HTTP status with an empty body), a dict (a JSON body), or an `httpx.Response`. A
    request for anything else fails the test."""

    def __init__(self, pages: dict | None = None, licence=None):
        self.pages = dict(pages or {})
        self.licence = licence
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        params = request.url.params
        if params.get("meta") == "siteinfo":
            value = self.licence
        elif params.get("action") == "parse" and params.get("page") in self.pages:
            value = self.pages[params["page"]]
        else:
            raise AssertionError(f"unexpected wiki request: {request.url}")
        if isinstance(value, httpx.Response):
            return value
        if isinstance(value, int):
            return httpx.Response(value)
        if isinstance(value, dict):
            return httpx.Response(200, json=value)
        raise AssertionError(f"no answer for {request.url}")

    def parse_requests(self, page: str | None = None) -> list[httpx.Request]:
        return [
            r
            for r in self.requests
            if r.url.params.get("action") == "parse" and (page is None or r.url.params.get("page") == page)
        ]


def wiki_client(cache_dir: Path, server: WikiServer | None = None, seed: bool = True) -> tuple[WikiClient, WikiServer]:
    """A client on `cache_dir` (seeded with the fixtures unless `seed` is False), never sleeping,
    whose requests all go to `server`."""
    server = server or WikiServer()
    if seed:
        seed_cache(cache_dir)
    return WikiClient(cache_dir, transport=httpx.MockTransport(server), min_interval=0), server
