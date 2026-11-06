"""Entry provenance rules (R2.S). Shared by the proposal tool (so the card shows what will be
stored) and the commit (the guard)."""

from sagaloom.models import Entry, EntryDraft

# The heading an import merge puts before the appended passage: `## Imported from <label> (<date>)`
# (R2.S per-section provenance). Shared by the import merge and Save as myth.
IMPORTED_HEADING = "## Imported from "


def merge_provenance(before: Entry, draft: EntryDraft) -> dict:
    """Provenance fails closed across updates: once untrusted, always untrusted; a non-`user`
    source is never downgraded to `user`; a new `source_url`/`licence` wins, else the old one."""
    return {
        "trusted": before.trusted and draft.trusted,
        "source": before.source if draft.source == "user" else draft.source,
        "source_url": draft.source_url or before.source_url,
        "licence": draft.licence or before.licence,
    }


def is_import_merge(before_body: str, after_body: str) -> bool:
    """True when `after_body` is `before_body` with an imported section appended, as an import
    merge builds it: the stored body unchanged, then a blank line and the heading."""
    head = before_body.rstrip()
    return after_body.startswith(head) and after_body[len(head) :].startswith("\n\n" + IMPORTED_HEADING)
