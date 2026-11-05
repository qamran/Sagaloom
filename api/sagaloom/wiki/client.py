"""A small MediaWiki client (R11.4.2, R11.4.4).

Only `*.wikipedia.org` over https is reachable: any other URL raises `HostNotAllowed` before a
request is made, and redirects are not followed, so a response can't move the client elsewhere.
Every response is cached on disk under `cache_dir`, keyed by the sha256 of the URL and served
without expiry. Failures are never cached.
"""

import asyncio
import hashlib
import json
import os
import uuid
from pathlib import Path
from urllib.parse import quote, urlencode

import httpx
from pydantic import BaseModel

USER_AGENT = "Sagaloom/0.2 (+https://github.com/qamran/Sagaloom)"
API = "https://en.wikipedia.org/w/api.php"
SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
PAGE = "https://en.wikipedia.org/wiki/"
SUMMARY_CAP = 1000


class HostNotAllowed(ValueError):
    """The URL is not an https URL on *.wikipedia.org."""


class RefResult(BaseModel):
    title: str
    summary: str
    url: str


def _allowed(url: httpx.URL) -> bool:
    host = (url.host or "").lower()
    return url.scheme == "https" and (host == "wikipedia.org" or host.endswith(".wikipedia.org"))


class WikiClient:
    def __init__(
        self,
        cache_dir: Path,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 10.0,
    ):
        self.cache_dir = Path(cache_dir)
        self._transport = transport
        self._timeout = timeout

    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / f"{hashlib.sha256(url.encode('utf-8')).hexdigest()}.json"

    def _read_cache(self, path: Path) -> dict | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None  # a missing or unreadable file is a miss
        return data if isinstance(data, dict) else None

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

    async def get_json(self, url: str) -> dict:
        """GET a JSON object. Raises `HostNotAllowed` (no request made), `httpx.HTTPError` on a
        network or HTTP failure, or `ValueError` when the body is not a JSON object."""
        if not _allowed(httpx.URL(url)):
            raise HostNotAllowed(f"only https://*.wikipedia.org is allowed, not {url!r}")
        path = self._cache_path(url)
        cached = await asyncio.to_thread(self._read_cache, path)
        if cached is not None:
            return cached
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=self._timeout,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=False,
        ) as http:
            resp = await http.get(url)
            resp.raise_for_status()
        data = resp.json()  # ValueError on a non-JSON body
        if not isinstance(data, dict):
            raise ValueError("the response is not a JSON object")
        await asyncio.to_thread(self._write_cache, path, data)
        return data


def search_url(query: str, limit: int) -> str:
    params = {"action": "query", "list": "search", "format": "json", "srlimit": limit, "srsearch": query}
    return f"{API}?{urlencode(params)}"


def _title_path(title: str) -> str:
    return quote(title.replace(" ", "_"), safe="")


def summary_url(title: str) -> str:
    return SUMMARY + _title_path(title)


def page_url(title: str) -> str:
    return PAGE + _title_path(title)


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
