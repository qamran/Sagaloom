"""Entry sources and merge precedence (R-W3-1): official before reference before first added;
`trusted` and NC never return once lost/gained."""

import json

from sagaloom.models import Entry, EntryDraft, EntrySource
from sagaloom.provenance import entry_is_nc, is_import_merge, merge_provenance, primary_source, union_sources

U1 = "https://en.wikipedia.org/wiki/Gandalf"
U2 = "https://lotr.fandom.com/wiki/Gandalf"
U3 = "https://example.org/ref"
T = "2026-01-01T00:00:00+00:00"


def ref(url, licence=None, **kw):
    return EntrySource(kind="reference", url=url, licence=licence, added_at=T, **kw)


def off(url, licence=None, **kw):
    return EntrySource(kind="official", url=url, licence=licence, added_at=T, **kw)


def entry(**kw):
    return Entry(id="ent_0001", world_id="w", title="Gandalf", type="character", body="A wizard.", **kw)


def draft(**kw):
    return EntryDraft(title="Gandalf", type="character", body="A wizard.", **kw)


def test_union_sources_dedupes_by_url_and_keeps_first():
    assert union_sources([ref(U1)], [off(U1, "X"), off(U2)]) == [ref(U1), off(U2)]


def test_primary_is_official_then_reference_then_first_added():
    assert primary_source([]) is None
    assert primary_source([ref(U1), ref(U3)]) == ref(U1)
    assert primary_source([ref(U1), off(U2), off(U3)]) == off(U2)


def test_wiki_merge_into_user_entry_becomes_official():
    before = entry()
    assert before.sources == [] and before.trusted
    wiki = draft(trusted=False, sources=[off(U1, "CC BY-SA 4.0")])
    got = merge_provenance(before, wiki)
    assert got["source"] == "official"
    assert got["source_url"] == U1
    assert got["licence"] == "CC BY-SA 4.0"
    assert got["trusted"] is False
    assert got["sources"] == [off(U1, "CC BY-SA 4.0")]


def test_reference_merge_never_replaces_official_primary():
    before = entry(trusted=False, sources=[off(U1, "CC BY-SA 4.0")])
    got = merge_provenance(before, draft(trusted=False, sources=[ref(U3)]))
    assert (got["source"], got["source_url"], got["licence"]) == ("official", U1, "CC BY-SA 4.0")
    assert got["sources"] == [off(U1, "CC BY-SA 4.0"), ref(U3)]


def test_nc_survives_any_merge():
    before = entry(trusted=False, sources=[off(U2, "CC BY-NC-SA 3.0", nc=True)])
    assert entry_is_nc(before)
    merged = Entry.model_validate(
        {**before.model_dump(), **merge_provenance(before, draft(trusted=False, sources=[off(U1, "CC BY-SA 4.0")]))}
    )
    assert entry_is_nc(merged)
    plain = Entry.model_validate({**merged.model_dump(), **merge_provenance(merged, draft())})
    assert entry_is_nc(plain)


def test_trusted_never_returns_after_wiki_merge():
    before = entry()
    once = Entry.model_validate(
        {**before.model_dump(), **merge_provenance(before, draft(trusted=False, sources=[off(U1)]))}
    )
    chat = draft(trusted=True, sources=[ref(U3)])
    twice = Entry.model_validate({**once.model_dump(), **merge_provenance(once, chat)})
    assert twice.trusted is False
    assert [s.url for s in twice.sources] == [U1, U3]


def test_legacy_entry_reads_one_source():
    stored = entry(source="reference", source_url=U3, trusted=False).model_dump()
    stored.pop("sources")
    got = Entry.model_validate_json(json.dumps(stored))
    assert got.sources == [
        EntrySource(kind="reference", url=U3, licence=None, nc=False, added_at=got.created_at)
    ]
    user = entry().model_dump()
    user.pop("sources")
    assert Entry.model_validate_json(json.dumps(user)).sources == []


URL = "https://en.wikipedia.org/wiki/Gandalf"
REIMPORT_BEFORE = (
    f"Grey pilgrim.\n\n## Imported from {URL} (2026-01-01)\n\nAn older lead.\n\n"
    "## Imported from notes.md (2026-01-02)\n\nThe author's own notes."
)


def test_import_merge_accepts_an_appended_section():
    assert is_import_merge("Old body.\n", f"Old body.\n\n## Imported from {URL} (2026-11-09)\n\nNew.")
    assert not is_import_merge("Old body.", "Rewritten body.")


def test_import_merge_accepts_one_section_replaced_in_place():
    """A re-import (Q1 (c)) replaces its own earlier section; the text around it is unchanged."""
    after = REIMPORT_BEFORE.replace(
        f"## Imported from {URL} (2026-01-01)\n\nAn older lead.", f"## Imported from {URL} (2026-11-09)\n\nA fresh lead."
    )
    assert is_import_merge(REIMPORT_BEFORE, after)


def test_import_merge_refuses_a_change_outside_the_replaced_section():
    fresh = f"## Imported from {URL} (2026-11-09)\n\nA fresh lead."
    old = f"## Imported from {URL} (2026-01-01)\n\nAn older lead."
    edited_head = REIMPORT_BEFORE.replace(old, fresh).replace("Grey pilgrim.", "White rider.")
    edited_tail = REIMPORT_BEFORE.replace(old, fresh).replace("own notes", "rewritten notes")
    assert not is_import_merge(REIMPORT_BEFORE, edited_head)
    assert not is_import_merge(REIMPORT_BEFORE, edited_tail)
    # A section for another label is not a replacement of this one.
    other = REIMPORT_BEFORE.replace(old, "## Imported from https://x.org/wiki/Y (2026-11-09)\n\nA fresh lead.")
    assert not is_import_merge(REIMPORT_BEFORE, other)
