"""Wiki page URLs (R-W3-8, R-W3-12): which pasted links name an article, and the MediaWiki API
URLs built from them.

Only article pages on `<label>.wikipedia.org` and `<label>.fandom.com` (optionally under a
`/<lang>` path on Fandom) are accepted. Every API URL is built here from the parsed host and
title, never taken from a response.
"""

import re
from urllib.parse import quote, unquote, urlencode

import httpx
from pydantic import BaseModel

ALLOWED_DOMAINS = ("wikipedia.org", "fandom.com")
MAX_URLS = 10
_SHOWN = 80  # a refused line is quoted back cut to this many characters

_COUNT = f"Paste 1 to {MAX_URLS} page URLs, one per line."
_NOT_A_PAGE = "Not a wiki page URL: {}. Use a page link such as https://en.wikipedia.org/wiki/Gandalf."
_NOT_ALLOWED = "Only Wikipedia and Fandom pages can be imported: {}"
_NOT_ARTICLE = "Only article pages can be imported, not category, file or special pages: {}"
_MIXED = "All URLs in one import must come from the same wiki."
_TWICE = "This page is listed twice: {}"

_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_WIKIPEDIA_PATH = re.compile(r"/wiki/(?P<title>.+)")
_FANDOM_PATH = re.compile(r"(?:/(?P<lang>[a-z]{2,3}(?:-[a-z]+)?))?/wiki/(?P<title>.+)")
_NAMESPACES = frozenset(
    {
        "category",
        "file",
        "image",
        "special",
        "template",
        "help",
        "user",
        "talk",
        "wikipedia",
        "project",
        "mediawiki",
        "portal",
        "module",
        "draft",
        "media",
    }
)
_NOT_A_LANGUAGE = frozenset({"www", "m"})
_TITLE_SAFE = "()!*',:;@$"


class BadWikiUrl(ValueError):
    """A pasted URL list was refused; `str(e)` is the copy shown to the user."""


class WikiPage(BaseModel):
    host: str
    lang_path: str  # "" or "/de"
    title: str  # spaces, not underscores
    url: str  # normalised


def host_allowed(url: httpx.URL) -> bool:
    """True for a plain https URL on a Wikipedia or Fandom host: no userinfo, default port, and no
    trailing dot."""
    host = (url.host or "").lower()
    return (
        url.scheme == "https"
        and not url.userinfo
        and url.port in (None, 443)
        and not host.endswith(".")
        and any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS)
    )


def _shown(raw: str) -> str:
    return raw[:_SHOWN]


def _wiki_label(host: str, domain: str) -> str | None:
    """The one DNS label in front of `domain`, or None when the host has another shape."""
    suffix = "." + domain
    if not host.endswith(suffix):
        return None
    label = host[: -len(suffix)]
    if domain == "wikipedia.org":
        if label.endswith(".m"):
            label = label[:-2]  # the phone site names the same page (R-W3-12)
        if label in _NOT_A_LANGUAGE:
            return None  # the portal and the bare phone site are not a wiki
    return label if _LABEL.fullmatch(label) else None


def _is_namespaced(title: str) -> bool:
    if ":" not in title:
        return False
    prefix = title.split(":", 1)[0].strip().lower()
    if prefix.endswith(" talk"):
        prefix = prefix[: -len(" talk")].strip()
    return prefix in _NAMESPACES


def _title_path(title: str) -> str:
    return quote(title.replace(" ", "_"), safe=_TITLE_SAFE)


def page_url(host: str, lang_path: str, title: str) -> str:
    return f"https://{host}{lang_path}/wiki/{_title_path(title)}"


def parse_page_url(raw: str) -> WikiPage:
    """One pasted line as an article page, or `BadWikiUrl` with the copy for why not."""
    line = raw.strip()
    try:
        url = httpx.URL(line)
    except (httpx.InvalidURL, TypeError, ValueError):
        raise BadWikiUrl(_NOT_A_PAGE.format(_shown(line))) from None
    if not url.scheme or not url.host:
        raise BadWikiUrl(_NOT_A_PAGE.format(_shown(line)))
    if not host_allowed(url):
        raise BadWikiUrl(_NOT_ALLOWED.format(_shown(line)))

    host = url.host.lower()
    path = url.raw_path.decode("ascii").split("?", 1)[0]
    lang_path = ""
    if (label := _wiki_label(host, "wikipedia.org")) is not None:
        host = f"{label}.wikipedia.org"
        match = _WIKIPEDIA_PATH.fullmatch(path)
    elif (label := _wiki_label(host, "fandom.com")) is not None:
        match = _FANDOM_PATH.fullmatch(path)
        if match and match["lang"]:
            lang_path = "/" + match["lang"]
    else:
        match = None
    if match is None:
        raise BadWikiUrl(_NOT_A_PAGE.format(_shown(line)))

    title = unquote(match["title"]).replace("_", " ").strip()
    if not title:
        raise BadWikiUrl(_NOT_A_PAGE.format(_shown(line)))
    if _is_namespaced(title):
        raise BadWikiUrl(_NOT_ARTICLE.format(_shown(line)))
    return WikiPage(host=host, lang_path=lang_path, title=title, url=page_url(host, lang_path, title))


def page_key(p: WikiPage) -> tuple[str, str, str]:
    """Two URLs with equal keys name one page: MediaWiki folds only the title's first letter."""
    return (p.host, p.lang_path, p.title[:1].upper() + p.title[1:])


def parse_page_urls(text_or_lines: str | list[str]) -> list[WikiPage]:
    """Every non-blank line as a page, all from one wiki and none twice. The first failure
    raises `BadWikiUrl`."""
    lines = text_or_lines.splitlines() if isinstance(text_or_lines, str) else list(text_or_lines)
    lines = [line for line in lines if line.strip()]
    if not 1 <= len(lines) <= MAX_URLS:
        raise BadWikiUrl(_COUNT)
    pages = [parse_page_url(line) for line in lines]
    if len({(p.host, p.lang_path) for p in pages}) > 1:
        raise BadWikiUrl(_MIXED)
    seen: set[tuple[str, str, str]] = set()
    for line, page in zip(lines, pages, strict=True):
        key = page_key(page)
        if key in seen:
            raise BadWikiUrl(_TWICE.format(_shown(line.strip())))
        seen.add(key)
    return pages


def api_url(host: str, lang_path: str) -> str:
    if host == "fandom.com" or host.endswith(".fandom.com"):
        return f"https://{host}{lang_path}/api.php"
    if host == "wikipedia.org" or host.endswith(".wikipedia.org"):
        return f"https://{host}/w/api.php"
    raise ValueError(f"not a Wikipedia or Fandom host: {host!r}")


def parse_request_url(p: WikiPage) -> str:
    params = {
        "action": "parse",
        "format": "json",
        "formatversion": 2,
        "page": p.title,
        "prop": "wikitext|categories",
        "redirects": 1,
    }
    return f"{api_url(p.host, p.lang_path)}?{urlencode(params)}"


def rightsinfo_url(host: str, lang_path: str = "") -> str:
    params = {"action": "query", "meta": "siteinfo", "siprop": "rightsinfo", "format": "json", "formatversion": 2}
    return f"{api_url(host, lang_path)}?{urlencode(params)}"
