"""The shared MediaWiki client (R11.4.2, R11.4.4, R11.4.8, R-W3-2, R-W3-9).

Only https Wikipedia and Fandom hosts are reachable (`pages.host_allowed`): any other URL raises
`HostNotAllowed` before a request is made, and so does a redirect hop to one, so a response can't
move the client elsewhere. At most five redirect hops are followed. Requests carry an honest
User-Agent, wait `min_interval` seconds between real requests to one host, and are never retried.
Every successful response is cached on disk under `cache_dir`, keyed by the sha256 of the URL and
served without expiry. Failures and MediaWiki error bodies are never cached.
"""

import asyncio
import hashlib
import importlib.metadata
import json
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from urllib.parse import quote, urlencode

import httpx
from pydantic import BaseModel

from sagaloom.licence import is_nc
from sagaloom.wiki import pages
from sagaloom.wiki.pages import WikiPage, host_allowed


def _version() -> str:
    try:
        return importlib.metadata.version("sagaloom")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


USER_AGENT = f"Sagaloom/{_version()} (+https://github.com/qamran/Sagaloom)"
API = "https://en.wikipedia.org/w/api.php"
SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
SUMMARY_CAP = 1000
MAX_REDIRECTS = 5
MIN_INTERVAL = 1.0
_REDIRECTS = frozenset({301, 302, 303, 307, 308})


class HostNotAllowed(ValueError):
    """The URL, or a redirect hop, is not a plain https URL on a Wikipedia or Fandom host."""


class WikiApiError(ValueError):
    """MediaWiki answered with an `error` body; `code` is its `error.code`."""

    def __init__(self, code: str):
        super().__init__(f"MediaWiki error: {code}")
        self.code = code


class LicenceUnreadable(Exception):
    """The wiki's licence could not be read, so nothing from it may be imported (R-W3-2)."""

    def __init__(self, host: str):
        super().__init__(
            f"Couldn't read the licence of {host}, so nothing was imported. "
            "A licence is never assumed: try again later, or paste the text instead."
        )
        self.host = host


class SiteLicence(BaseModel):
    text: str | None
    url: str | None
    nc: bool

    @property
    def display(self) -> str:
        return self.text or self.url or "licence not reported"


class FetchedPage(BaseModel):
    page: WikiPage
    title: str  # after MediaWiki redirects
    url: str  # built from the final host and `title`, never taken from the response
    wikitext: str
    categories: list[str]
    revid: int | None


class RefResult(BaseModel):
    title: str
    summary: str
    url: str


def _non_empty_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


class WikiClient:
    def __init__(
        self,
        cache_dir: Path,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 10.0,
        min_interval: float = MIN_INTERVAL,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.cache_dir = Path(cache_dir)
        self._transport = transport
        self._timeout = timeout
        self._min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._http: httpx.AsyncClient | None = None  # created on first use, inside the loop
        self._locks: dict[str, asyncio.Lock] = {}
        self._last: dict[str, float] = {}

    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / f"{hashlib.sha256(url.encode('utf-8')).hexdigest()}.v2.json"

    def _read_cache(self, path: Path) -> tuple[dict, str] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None  # a missing or unreadable file is a miss
        if not isinstance(data, dict):
            return None
        body, final_url = data.get("body"), data.get("final_url")
        if not isinstance(body, dict) or not isinstance(final_url, str):
            return None
        return body, final_url

    def _write_cache(self, path: Path, data: dict) -> None:
        # Best effort: a failed write (e.g. two concurrent writers on Windows) must not fail the
        # lookup. Write to a temp name, then rename, so a reader never sees half a file.
        tmp = path.with_name(f"{path.stem}.{uuid.uuid4().hex}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                transport=self._transport,
                timeout=self._timeout,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=False,
            )
        return self._http

    async def aclose(self) -> None:
        http, self._http = self._http, None
        if http is not None:
            await http.aclose()

    async def _request(self, url: httpx.URL) -> httpx.Response:
        """One real GET, at least `min_interval` after the last one to the same host."""
        host = url.host
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            if host in self._last:
                wait = self._min_interval - (self._clock() - self._last[host])
                if wait > 0:
                    await self._sleep(wait)
            try:
                return await self._client().get(url)
            finally:
                self._last[host] = self._clock()

    async def _fetch(self, url: str) -> tuple[dict, str]:
        """GET `url`, following at most `MAX_REDIRECTS` hops, each checked against the allowlist
        before it is requested."""
        current = httpx.URL(url)
        for hop in range(MAX_REDIRECTS + 1):
            resp = await self._request(current)
            if resp.status_code in _REDIRECTS and "location" in resp.headers:
                if hop == MAX_REDIRECTS:
                    raise httpx.TooManyRedirects(
                        f"more than {MAX_REDIRECTS} redirects from {url!r}", request=resp.request
                    )
                target = current.join(resp.headers["location"])
                if not host_allowed(target):
                    raise HostNotAllowed(f"refused a redirect off the allowed hosts to {str(target)!r}")
                current = target
                continue
            resp.raise_for_status()  # no status is retried
            data = resp.json()  # ValueError on a non-JSON body
            if not isinstance(data, dict):
                raise ValueError("the response is not a JSON object")
            return data, str(current)
        raise AssertionError("unreachable")  # every pass of the loop returns, raises or continues

    async def get_json_final(self, url: str) -> tuple[dict, str]:
        """GET a JSON object, following allowed redirects; returns the body and the final URL.
        Raises `HostNotAllowed` (no request made to that host), `httpx.HTTPError` on a network
        or HTTP failure or too many redirects, or `ValueError` when the body is not a JSON
        object. A body with a top-level `error` is returned but not cached."""
        if not host_allowed(httpx.URL(url)):
            raise HostNotAllowed(f"only https Wikipedia and Fandom hosts are allowed, not {url!r}")
        path = self._cache_path(url)
        cached = await asyncio.to_thread(self._read_cache, path)
        if cached is not None:
            return cached
        body, final_url = await self._fetch(url)
        if "error" not in body:
            await asyncio.to_thread(self._write_cache, path, {"final_url": final_url, "body": body})
        return body, final_url

    async def get_json(self, url: str) -> dict:
        """`get_json_final` without the final URL."""
        body, _ = await self.get_json_final(url)
        return body

    async def fetch_page(self, page: WikiPage) -> FetchedPage:
        """The page's wikitext and categories from `action=parse`. Raises `WikiApiError` for a
        MediaWiki error body, `ValueError` for a reply without a usable parse result, and
        otherwise as `get_json_final` does."""
        body, final_url = await self.get_json_final(pages.parse_request_url(page))
        if "error" in body:
            error = body["error"]
            code = error.get("code") if isinstance(error, dict) else None
            raise WikiApiError(code if isinstance(code, str) else "unknown")
        parse = body.get("parse")
        if not isinstance(parse, dict):
            raise ValueError("the response has no parse result")
        title, wikitext = parse.get("title"), parse.get("wikitext")
        if not isinstance(title, str) or not title.strip() or not isinstance(wikitext, str):
            raise ValueError("the parse result has no title or wikitext")
        revid = parse.get("revid")
        return FetchedPage(
            page=page,
            title=title,
            url=pages.page_url(httpx.URL(final_url).host, page.lang_path, title),
            wikitext=wikitext,
            categories=[
                c["category"]
                for c in parse.get("categories") or []
                if isinstance(c, dict) and isinstance(c.get("category"), str)
            ],
            revid=revid if isinstance(revid, int) and not isinstance(revid, bool) else None,
        )

    async def site_licence(self, host: str, lang_path: str = "") -> SiteLicence:
        """The wiki's licence exactly as `rightsinfo` reports it. Raises `LicenceUnreadable` on
        any failure, or when it reports neither a text nor a URL (R-W3-2)."""
        try:
            body = await self.get_json(pages.rightsinfo_url(host, lang_path))
            query = body.get("query")
            info = query.get("rightsinfo") if isinstance(query, dict) else None
            if "error" in body or not isinstance(info, dict):
                raise ValueError("no rightsinfo in the response")
        except Exception as e:
            raise LicenceUnreadable(host) from e
        text, url = _non_empty_str(info.get("text")), _non_empty_str(info.get("url"))
        if text is None and url is None:
            raise LicenceUnreadable(host)
        return SiteLicence(text=text, url=url, nc=is_nc(text, url))


def search_url(query: str, limit: int) -> str:
    params = {"action": "query", "list": "search", "format": "json", "srlimit": limit, "srsearch": query}
    return f"{API}?{urlencode(params)}"


def summary_url(title: str) -> str:
    # A REST path segment, not a page URL: everything, "/" included, is percent-encoded.
    return SUMMARY + quote(title.replace(" ", "_"), safe="")


def page_url(title: str) -> str:
    """The English Wikipedia page URL, encoded exactly as an imported page's (`pages.page_url`),
    so one page always has one URL."""
    return pages.page_url("en.wikipedia.org", "", title)


def cap_summary(text: str, limit: int = SUMMARY_CAP) -> str:
    """At most `limit` characters, cut at a word boundary and ended with "…" when cut."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip() + "…"


async def search_and_summarise(client: WikiClient, query: str, max_results: int) -> list[RefResult]:
    """Search English Wikipedia, then fetch each hit's REST summary. Any failure raises."""
    found = await client.get_json(search_url(query, max_results))
    titles = [
        h["title"]
        for h in (found.get("query") or {}).get("search") or []
        if isinstance(h, dict) and isinstance(h.get("title"), str)
    ][:max_results]
    summaries = await asyncio.gather(*(client.get_json(summary_url(t)) for t in titles))
    return [
        RefResult(
            title=t,
            summary=cap_summary(str(s.get("extract") or "")),
            url=page_url(t),  # built here, never taken from the response
        )
        for t, s in zip(titles, summaries, strict=True)
    ]
