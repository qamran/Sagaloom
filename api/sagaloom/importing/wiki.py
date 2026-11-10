"""Fan-wiki import (R-W3-1..R-W3-5, R13.6, R13.7; M3 design §5).

A wiki page is untrusted text. Each page is fetched through the shared `WikiClient`, stripped to
plain text, and sent to the extractor alone, wrapped as data under a `Page title:` label, with no
tools bound. The model only points at a passage: the stored body is the slice of the stripped
text that `locate` finds, never the model's own prose. Every proposal is `trusted=False` with an
`official` source that records the wiki's licence exactly as the wiki reported it, and goes
through the check and the approval gate like any other.
"""

import asyncio
import logging
import uuid
from datetime import date
from typing import TYPE_CHECKING

import httpx
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ValidationError

from sagaloom.importing.extract import (
    BODY_MAX,
    ENTRY_FULL,
    EXTRACT_SYSTEM,
    INVALID,
    NOT_LOCATED,
    PART_FAILED,
    TITLE_CHARS,
    Candidate,
    ImportPlan,
    Skipped,
    _extract,
    _resolve,
    _valid_facts,
    fit,
    locate,
    merge_facts,
)
from sagaloom.importing.wikitext import StrippedPage, strip_wikitext, type_from_infobox
from sagaloom.models import Entry, EntryDraft, EntrySource, EntryType, Proposal
from sagaloom.provenance import IMPORTED_HEADING, merge_provenance, provenance_fields, section_span
from sagaloom.store.canon import norm
from sagaloom.text import first_line
from sagaloom.wiki.client import FetchedPage, HostNotAllowed, SiteLicence, WikiApiError, WikiClient
from sagaloom.wiki.pages import WikiPage, is_article_title, page_key

if TYPE_CHECKING:
    from sagaloom.structured import ChatModelLike

log = logging.getLogger(__name__)

# Not-imported reasons (`Skipped.reason`); the ones a pasted text could replace have `paste=True`.
BLOCKED = "the wiki refused the request (HTTP {code})"
RATE_LIMITED = "the wiki asked us to slow down (HTTP 429)"
PAGE_MISSING = "the page does not exist"
NOT_REQUESTED = "not requested: the wiki refused an earlier page"
UNREACHABLE = "the wiki could not be reached"
NO_TEXT = "the page has no article text"
SAME_PAGE = "the same page as another URL in this import"
LICENCE_UNREADABLE = (
    "Couldn't read the licence of {host}, so nothing was imported. "
    "A licence is never assumed: try again later, or paste the text instead."
)
NOTE_CONTENT = "Imported wiki pages: {} proposals for review, {} not imported."

WIKI_EXTRACT_SYSTEM = (
    EXTRACT_SYSTEM
    + " The text is one wiki page. Its first line is `Page title: …`. Emit exactly one candidate: "
    "the page's subject. Its excerpt is the passage that best describes the subject, copied exactly."
)

_MISSING_CODES = frozenset({"missingtitle", "invalidtitle"})
_BLOCK_STATUSES = frozenset({402, 403})


class WikiFetch(BaseModel):
    host: str
    lang_path: str
    licence: SiteLicence
    pages: list[FetchedPage]
    skipped: list[Skipped]
    requested: int  # the number of URLs sent


def _failure_reason(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in _BLOCK_STATUSES:
            return BLOCKED.format(code=status)
        if status == 429:
            return RATE_LIMITED
        if status == 404:
            return PAGE_MISSING
    if isinstance(exc, WikiApiError) and exc.code in _MISSING_CODES:
        return PAGE_MISSING
    return UNREACHABLE  # a timeout, a network error, a 5xx, a redirect off the allowlist, a bad body


def _final_page(p: FetchedPage) -> WikiPage:
    """The page MediaWiki resolved `p.page` to, after any redirect."""
    return WikiPage(host=httpx.URL(p.url).host, lang_path=p.page.lang_path, title=p.title, url=p.url)


async def fetch_wiki(client: WikiClient, pages: list[WikiPage]) -> WikiFetch:
    """The wiki's licence, then each page in input order, one at a time. `LicenceUnreadable`
    propagates before any page is requested (R-W3-2). After a 402/403 no later page is requested
    (R-W3-3). Two URLs that resolve to one page give one fetched page."""
    if not pages:
        raise ValueError("no pages to fetch")
    host, lang_path = pages[0].host, pages[0].lang_path
    licence = await client.site_licence(host, lang_path)
    fetched: list[FetchedPage] = []
    skipped: list[Skipped] = []
    seen: set[tuple[str, str, str]] = set()
    blocked = False
    for page in pages:
        title = page.title[:TITLE_CHARS]
        if blocked:
            skipped.append(Skipped(title=title, reason=NOT_REQUESTED, paste=True))
            continue
        try:
            got = await client.fetch_page(page)
        except Exception as exc:
            reason = _failure_reason(exc)
            # An HTTP or MediaWiki failure is the wiki's; anything else may be a bug here, so it
            # keeps its traceback (still listed as unreachable).
            expected = isinstance(exc, (httpx.HTTPError, WikiApiError, HostNotAllowed))
            log.log(
                logging.INFO if expected else logging.WARNING,
                "wiki page %r not fetched: %s", page.url, reason, exc_info=not expected,
            )
            blocked = isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in _BLOCK_STATUSES
            skipped.append(Skipped(title=title, reason=reason, paste=True))
            continue
        if not is_article_title(got.title):
            # A redirect landed on a non-article page (`WP:NPOV` -> `Wikipedia:...`).
            skipped.append(Skipped(title=title, reason=PAGE_MISSING, paste=True))
            continue
        key = page_key(_final_page(got))
        if key in seen:
            skipped.append(Skipped(title=title, reason=SAME_PAGE))
            continue
        seen.add(key)
        fetched.append(got)
    return WikiFetch(
        host=host, lang_path=lang_path, licence=licence, pages=fetched, skipped=skipped, requested=len(pages)
    )


def extraction_text(stripped: StrippedPage) -> str:
    """The text the extractor reads and `locate` searches: the lead section, infobox lines
    included (Open question 2 (a))."""
    return stripped.text[: stripped.lead_end]


def _lead_has_prose(s: StrippedPage) -> bool:
    """True when the extracted text, the lead, holds more than the infobox lines, so a body can
    never be infobox lines alone. Each infobox value is one line, and the infobox block is set
    off from the prose by a blank line."""
    lead = extraction_text(s).strip()
    if not lead:
        return False
    if any(v for v in s.infobox.values()):
        return "\n\n" in lead
    return True


def _pick(cands: list[Candidate], title: str) -> Candidate | None:
    """The candidate named like the page, by its title or an alias, else the first (R-W3-5)."""
    want = norm(title)
    for c in cands:
        if want in {norm(n) for n in [c.title, *c.aliases]}:
            return c
    return cands[0] if cands else None


def _merged_body(before: Entry, url: str, excerpt: str, today: date) -> tuple[str, str] | None:
    """(body, fitted excerpt) for a merge: the passage under its heading, appended, or in place of
    this page's earlier section when the page is already a source (Open question 1 (c)). None
    when it doesn't fit."""
    heading = f"{IMPORTED_HEADING}{url} ({today:%Y-%m-%d})"
    span = section_span(before.body, url) if any(s.url == url for s in before.sources) else None
    if span is None:
        prefix, suffix = before.body.rstrip() + f"\n\n{heading}\n\n", ""
    else:
        head, tail = before.body[: span[0]].rstrip(), before.body[span[1] :].strip()
        prefix = (head + "\n\n" if head else "") + heading + "\n\n"
        suffix = "\n\n" + tail if tail else ""
    fitted = fit(excerpt, BODY_MAX - len(prefix) - len(suffix))
    if fitted is None:
        return None
    return prefix + fitted + suffix, fitted


def _proposal(
    world_id: str, p: FetchedPage, cand: Candidate, excerpt: str, entry_type: EntryType,
    source: EntrySource, before: Entry | None, today: date,
) -> tuple[Proposal, str] | str:
    """(proposal, fitted excerpt), or the reason the page was not imported."""
    facts = _valid_facts(cand.facts)
    pid = "p_" + uuid.uuid4().hex[:8]
    try:
        if before is None:
            body = fit(excerpt, BODY_MAX)
            if body is None:
                return ENTRY_FULL
            title = p.title[:TITLE_CHARS]
            aliases: list[str] = []
            for a in cand.aliases:
                if norm(a) != norm(title) and norm(a) not in {norm(x) for x in aliases}:
                    aliases.append(a)
            after = EntryDraft(
                title=title,
                type=entry_type,
                body=body,
                status="canon",
                aliases=aliases,
                facts=facts,
                **provenance_fields([source], trusted=False),
            )
            return Proposal(
                proposal_id=pid, action="create", world_id=world_id, entry_id=None, before=None, after=after,
                imported=True,
            ), body
        merged = _merged_body(before, p.url, excerpt, today)
        if merged is None:
            return ENTRY_FULL
        body, fitted = merged
        imported = EntryDraft.model_construct(
            source="official", source_url=p.url, licence=source.licence, trusted=False, sources=[source]
        )
        after = EntryDraft(
            title=before.title,
            type=before.type,
            body=body,
            status=before.status,
            aliases=list(before.aliases),
            facts=merge_facts(before.facts, facts),
            **merge_provenance(before, imported),
        )
        return Proposal(
            proposal_id=pid, action="update", world_id=world_id, entry_id=before.id, before=before, after=after,
            imported=True,
        ), fitted
    except ValidationError:
        log.warning("wiki page %r is not a valid entry", p.title[:TITLE_CHARS], exc_info=True)
        return INVALID


async def build_wiki_import(
    store,
    llm: "ChatModelLike",
    world_id: str,
    fetched: WikiFetch,
    config: RunnableConfig | None = None,
    today: date | None = None,
) -> ImportPlan:
    """One extraction per fetched page, in order; each located subject becomes a create or a
    merge update. The plan's `skipped` lists the pages not fetched, then the ones not imported."""
    today = today or date.today()
    lic = fetched.licence
    skipped = list(fetched.skipped)
    proposals: list[Proposal] = []
    first_lines: dict[str, str] = {}
    parts = failed = 0
    # One read of canon for the whole import, off the event loop (Chroma is synchronous).
    index = await asyncio.to_thread(store.name_index, world_id)
    for p in fetched.pages:
        title = p.title[:TITLE_CHARS]
        s = strip_wikitext(p.wikitext)
        if not _lead_has_prose(s):
            skipped.append(Skipped(title=title, reason=NO_TEXT))
            continue
        text = extraction_text(s)
        parts += 1
        # The label is inside the wrapper only: it is never part of the text `locate` searches.
        result = await _extract(
            llm, f"Page title: {p.title}\n\n" + text, f"wiki:{fetched.host}/{p.title}", config,
            system=WIKI_EXTRACT_SYSTEM,
        )
        if result is None:
            failed += 1
            skipped.append(Skipped(title=title, reason=PART_FAILED))
            continue
        cands, invalid = result
        cand = _pick(cands, p.title)
        if cand is None:
            skipped.append(Skipped(title=title, reason=INVALID if invalid else NOT_LOCATED))
            continue
        excerpt = locate(cand.excerpt, text)
        if excerpt is None:
            skipped.append(Skipped(title=title, reason=NOT_LOCATED))
            continue
        source = EntrySource(kind="official", url=p.url, licence=lic.text, licence_url=lic.url, nc=lic.nc)
        before = _resolve(index, cand.model_copy(update={"title": p.title}))
        entry_type = type_from_infobox(s.infobox_name) or cand.type
        made = _proposal(world_id, p, cand, excerpt, entry_type, source, before, today)
        if isinstance(made, str):
            skipped.append(Skipped(title=(before.title if before else title)[:TITLE_CHARS], reason=made))
            continue
        proposal, body = made
        proposals.append(proposal)
        first_lines[proposal.proposal_id] = first_line(body)[:TITLE_CHARS]
    return ImportPlan(
        proposals=proposals,
        skipped=skipped,
        first_lines=first_lines,
        failed_parts=failed,
        parts=parts,
        licence=licence_dict(lic),
    )


def licence_dict(lic: SiteLicence) -> dict:
    return {"text": lic.text, "url": lic.url, "nc": lic.nc}
