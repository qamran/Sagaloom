"""Possible-duplicate notes for a new entry (spec §3.9). A note only: it never changes a verdict."""

import logging
import re

from sagaloom.models import Entry, EntryDraft, Flag
from sagaloom.store.canon import norm

log = logging.getLogger(__name__)

STOPWORDS = frozenset({"the", "a", "an", "of"})
OVERLAP = 0.6
SEARCH_SCORE = 0.92
MAX_FLAGS = 3


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", norm(text))) - STOPWORDS


def _overlaps(a: set[str], b: set[str]) -> bool:
    return bool(a and b) and len(a & b) / max(len(a), len(b)) >= OVERLAP


def _flag(entry: Entry) -> Flag:
    return Flag(
        kind="note",
        entry_id=entry.id,
        title=entry.title,
        severity="note",
        explanation=f"Possible duplicate of {entry.id} '{entry.title}'",
        existing_secret=entry.status == "secret",
    )


def duplicate_flags(store, world_id: str, draft: EntryDraft) -> list[Flag]:
    """At most one flag per entry and MAX_FLAGS in all: a near-identical top search hit first,
    then titles or aliases sharing most of the draft title's words, in entry-id order."""
    entries = store.list_entries(world_id)
    wanted = _tokens(draft.title)
    matched = {
        e.id
        for e in entries
        if any(_overlaps(wanted, _tokens(name)) for name in (e.title, *e.aliases))
    }
    try:
        hits = store.search(world_id, draft.title, k=1)
    except Exception:  # the token match still stands when search is down
        log.warning("Duplicate search failed in %s", world_id, exc_info=True)
        hits = []
    by_id = {e.id: e for e in entries}
    first = [hits[0].id] if hits and hits[0].score >= SEARCH_SCORE and hits[0].id in by_id else []
    order = [*first, *(e.id for e in entries if e.id in matched and e.id not in first)]
    return [_flag(by_id[i]) for i in order[:MAX_FLAGS]]
