"""Entry provenance rules (R2.S). Shared by the proposal tool (so the card shows what will be
stored) and the commit (the guard)."""

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
    sources = union_sources(before.sources, getattr(draft, "sources", None) or [])
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


def is_import_merge(before_body: str, after_body: str) -> bool:
    """True when `after_body` is `before_body` with an imported section appended, as an import
    merge builds it: the stored body unchanged, then a blank line and the heading."""
    head = before_body.rstrip()
    return after_body.startswith(head) and after_body[len(head) :].startswith("\n\n" + IMPORTED_HEADING)
