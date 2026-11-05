"""Entry provenance rules (R2.S). Shared by the proposal tool (so the card shows what will be
stored) and the commit (the guard)."""

from sagaloom.models import Entry, EntryDraft


def merge_provenance(before: Entry, draft: EntryDraft) -> dict:
    """Provenance fails closed across updates: once untrusted, always untrusted; a non-`user`
    source is never downgraded to `user`; a new `source_url`/`licence` wins, else the old one."""
    return {
        "trusted": before.trusted and draft.trusted,
        "source": before.source if draft.source == "user" else draft.source,
        "source_url": draft.source_url or before.source_url,
        "licence": draft.licence or before.licence,
    }
