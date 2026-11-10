"""Entry provenance rules (R2.S). Shared by the proposal tool (so the card shows what will be
stored) and the commit (the guard)."""

import re

from sagaloom.models import Entry, EntryDraft, EntrySource

# The heading an import merge puts before the appended passage: `## Imported from <label> (<date>)`
# (R2.S per-section provenance). Shared by the import merge and Save as myth.
IMPORTED_HEADING = "## Imported from "


def union_sources(old: list[EntrySource], new: list[EntrySource]) -> list[EntrySource]:
    """`old` in order, then each `new` source whose URL is not there yet: the first record of a
    URL is kept, so a later import can't rewrite an earlier licence (R-W3-1)."""
    seen = {s.url for s in old}
    out = list(old)
    for s in new:
        if s.url not in seen:
            seen.add(s.url)
            out.append(s)
    return out


def primary_source(sources: list[EntrySource]) -> EntrySource | None:
    """The source the entry's `source`/`source_url`/`licence` show: the first `official`, else
    the first `reference`, else none."""
    for kind in ("official", "reference"):
        for s in sources:
            if s.kind == kind:
                return s
    return None


def provenance_fields(sources: list[EntrySource], trusted: bool) -> dict:
    """The provenance fields of an entry with these sources; `user` when there is no primary."""
    p = primary_source(sources)
    return {
        "sources": list(sources),
        "trusted": trusted,
        "source": p.kind if p else "user",
        "source_url": p.url if p else None,
        "licence": p.licence if p else None,
    }


def merge_provenance(before: Entry, draft: EntryDraft) -> dict:
    """Provenance fails closed across updates: once untrusted, always untrusted; sources only
    accumulate (so an NC source is never dropped), and the primary follows precedence, then the
    first added. With no sources at all, a non-`user` source is never downgraded to `user` and a
    new `source_url`/`licence` wins, else the old one."""
    trusted = before.trusted and draft.trusted
    sources = union_sources(before.sources, draft.sources)
    if sources:
        return provenance_fields(sources, trusted)
    return {
        "sources": [],
        "trusted": trusted,
        "source": before.source if draft.source == "user" else draft.source,
        "source_url": draft.source_url or before.source_url,
        "licence": draft.licence or before.licence,
    }


def entry_is_nc(e: Entry | EntryDraft) -> bool:
    """True when any of the entry's sources is licensed for non-commercial use only."""
    return any(s.nc for s in e.sources)


_DATED = r" \(\d{4}-\d{2}-\d{2}\)[ \t]*$"
_ANY_SECTION = re.compile(rf"(?m)^{re.escape(IMPORTED_HEADING)}(?P<label>.+?){_DATED}")


def section_span(body: str, label: str) -> tuple[int, int] | None:
    """Where the first `## Imported from <label> (<date>)` section of `body` runs: from its
    heading to the next level-1 or level-2 heading, or the end. None when there is none."""
    head = re.search(rf"(?m)^{re.escape(IMPORTED_HEADING + label)}{_DATED}", body)
    if head is None:
        return None
    nxt = re.search(r"(?m)^#{1,2} ", body[head.end() :])
    return head.start(), head.end() + nxt.start() if nxt else len(body)


def is_import_merge(before_body: str, after_body: str) -> bool:
    """True when `after_body` is `before_body` with an imported section added, as an import merge
    builds it: either appended (the stored body unchanged, then a blank line and the heading), or,
    for a page imported again (R-W3 Q1 (c)), one dated section replaced in place by a section for
    the same label, with the text before and after it unchanged."""
    head = before_body.rstrip()
    if after_body.startswith(head) and after_body[len(head) :].startswith("\n\n" + IMPORTED_HEADING):
        return True
    for m in _ANY_SECTION.finditer(after_body):
        old = section_span(before_body, m["label"])
        new = section_span(after_body, m["label"])
        if old is None or new is None or new[0] != m.start():
            continue
        if (
            before_body[: old[0]].rstrip() == after_body[: new[0]].rstrip()
            and before_body[old[1] :].strip() == after_body[new[1] :].strip()
        ):
            return True
    return False
